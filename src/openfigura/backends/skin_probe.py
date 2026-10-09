"""Fixed-pose skin deformation diagnostics using local Blender CPU rendering."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

from openfigura.backends import base
from openfigura.core.glb_faces import _read


def validate_config(config):
    """Return an independent JSON-compatible configuration; reject ambiguity."""
    if not isinstance(config, dict) or set(config) - {'probes', 'resolution', 'samples', 'crop_extent_ratio'}:
        raise ValueError('unknown skin probe configuration keys')
    probes = config.get('probes')
    if not isinstance(probes, list) or not 1 <= len(probes) <= 8:
        raise ValueError('probes must be a nonempty list with at most eight entries')
    result = {'probes': [], 'resolution': config.get('resolution', 512),
              'samples': config.get('samples', 8), 'crop_extent_ratio': config.get('crop_extent_ratio', .2)}
    for key, low, high in [('resolution', 256, 2048), ('samples', 1, 128)]:
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f'{key} must be an integer in [{low}, {high}]')
    ratio = result['crop_extent_ratio']
    if type(ratio) not in (int, float) or not .05 <= ratio <= .5 or not math.isfinite(ratio):
        raise ValueError('crop_extent_ratio must be finite in [.05, .5]')
    for probe in probes:
        if not isinstance(probe, dict) or set(probe) != {'bone', 'axis', 'degrees', 'track_groups'}:
            raise ValueError('probe requires exactly bone, axis, degrees, track_groups')
        bone, axis, degrees, groups = (probe[k] for k in ('bone', 'axis', 'degrees', 'track_groups'))
        if not isinstance(bone, str) or not bone.strip() or axis not in ('X', 'Y', 'Z'):
            raise ValueError('probe requires exact nonempty bone and X/Y/Z axis')
        if type(degrees) not in (int, float) or not 0 < abs(degrees) <= 180 or not math.isfinite(degrees):
            raise ValueError('degrees must be finite, nonzero and within [-180, 180]')
        if (not isinstance(groups, list) or not groups or
                any(not isinstance(g, str) or not g.strip() for g in groups) or len(set(groups)) != len(groups)):
            raise ValueError('track_groups must be nonempty unique exact names')
        result['probes'].append({'bone': bone, 'axis': axis, 'degrees': degrees, 'track_groups': list(groups)})
    return result


def artifact_names(count):
    return ['skin-probe-report.json', 'skin-probe.blend', 'rest-full.png'] + [
        f'probe-{i:03d}-{view}.png' for i in range(1, count+1) for view in ('full', 'closeup')]


def validate_source(model):
    try:
        raw, doc, blob = _read(model)
        if doc.get('asset', {}).get('version') != '2.0' or 'uri' in doc['buffers'][0] or len(blob)-doc['buffers'][0]['byteLength'] > 3:
            raise ValueError('embedded GLB2 required')
        if doc.get('animations'):
            raise ValueError('fixed rest rig only: animations unsupported')
        images = doc.get('images', [])
        if not isinstance(images, list) or any(not isinstance(image, dict) or 'uri' in image for image in images):
            raise ValueError('external images unsupported; embedded images required')
        return raw
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('invalid GLB structure') from exc


def report_complete(report, settings):
    """Require bounded, internally consistent evidence, not just an exit-zero flag."""
    def digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
    def finite(value):
        if type(value) not in (int, float): return False
        try: return math.isfinite(value)
        except OverflowError: return False
    if not isinstance(report, dict) or type(report.get('schema_version')) is not int or report['schema_version'] != 1 or report.get('status') != 'complete':
        return False
    if any(report.get(k) is not False for k in ('skin_quality_accepted', 'collision_checked', 'collision_accepted')) or report.get('visual_approval') != 'pending':
        return False
    if not digest(report.get('source_sha256')) or report.get('source_unchanged') is not True or report.get('settings') != settings:
        return False
    baseline = report.get('baseline')
    if not isinstance(baseline, list) or not baseline: return False
    mesh_sizes = {}
    for mesh in baseline:
        if not isinstance(mesh, dict) or not isinstance(mesh.get('mesh'), str) or not mesh['mesh'] or mesh['mesh'] in mesh_sizes: return False
        vertices = mesh.get('vertices')
        if type(vertices) is not int or vertices <= 0: return False
        if not all(digest(mesh.get(key)) for key in ('world_positions_sha256', 'original_labels_sha256')): return False
        mesh_sizes[mesh['mesh']] = vertices
    probes = report.get('probes')
    if not isinstance(probes, list) or len(probes) != len(settings['probes']): return False
    for actual, expected in zip(probes, settings['probes']):
        if not isinstance(actual, dict) or any(actual.get(k) != v for k, v in expected.items()): return False
        if not isinstance(actual.get('meshes'), list) or not actual['meshes']: return False
        count = 0; seen = set()
        for mesh in actual['meshes']:
            if not isinstance(mesh, dict) or not isinstance(mesh.get('mesh'), str) or mesh['mesh'] not in mesh_sizes or mesh['mesh'] in seen: return False
            name = mesh['mesh']; seen.add(name)
            tracked, over = mesh.get('tracked_vertices'), mesh.get('over_002_world_units')
            if type(tracked) is not int or not 0 <= tracked <= mesh_sizes[name] or type(over) is not int or not 0 <= over <= tracked: return False
            count += tracked
            peak = mesh.get('peak_world_units'); quantiles = mesh.get('quantiles_world_units')
            if not isinstance(quantiles, dict) or set(quantiles) != {'0.5', '0.9', '0.95', '0.99'}: return False
            numbers = [quantiles[key] for key in ('0.5', '0.9', '0.95', '0.99')] + [peak]
            if any(not finite(n) or n < 0 for n in numbers) or numbers != sorted(numbers): return False
            samples = mesh.get('worst_samples')
            if not isinstance(samples, list) or len(samples) != min(tracked, 20): return False
            ids = set(); previous = peak
            for sample in samples:
                if not isinstance(sample, dict): return False
                index = sample.get('vertex_index'); label = sample.get('original_dominant_group')
                if type(index) is not int or not 0 <= index < mesh_sizes[name] or index in ids: return False
                ids.add(index)
                if label is not None and (not isinstance(label, str) or not label): return False
                displacement = sample.get('displacement_world_units')
                if not finite(displacement) or not 0 <= displacement <= previous: return False
                previous = displacement
                for key in ('rest_world', 'posed_world'):
                    xyz = sample.get(key)
                    if not isinstance(xyz, list) or len(xyz) != 3 or not all(finite(v) for v in xyz): return False
            if samples and samples[0]['displacement_world_units'] != peak: return False
            if not tracked and (peak != 0 or over != 0): return False
            if not digest(mesh.get('frozen_track_mask_sha256')): return False
        if count == 0 or seen != set(mesh_sizes): return False
    return True


class SkinProbeBackend:
    id = 'blender-skin-probe'
    kind = 'postprocess'

    def binary(self):
        from openfigura.core import registry  # noqa: F401
        from openfigura.backends.blender import BlenderBackend
        return BlenderBackend().binary()

    def capabilities(self):
        from openfigura.core.registry import Capabilities
        binary = self.binary()
        return Capabilities(bool(binary), reason='' if binary else 'blender not found', hardware='cpu',
            notes={'binary': binary, 'limits': 'Embedded GLB2 fixed rest rig, exactly one skinned armature; +Y front camera, local bone axes, CPU Cycles. Displacement is diagnostic; collision and visual approval remain untested.'})

    def probe(self, model: Path, output_dir: Path, config: dict):
        settings = validate_config(config)
        model, output_dir = Path(model).resolve(), Path(output_dir).absolute()
        if not model.is_file() or model.suffix.lower() != '.glb': raise ValueError('existing GLB model required')
        if output_dir.parent.is_symlink(): raise ValueError('refusing symlink output directory parent')
        if output_dir.exists() or output_dir.is_symlink(): raise ValueError('refusing existing output directory')
        source_sha = hashlib.sha256(validate_source(model)).hexdigest()
        binary = self.binary()
        if not binary: raise RuntimeError('blender unavailable')
        output_dir.mkdir(parents=True, exist_ok=False)
        names = artifact_names(len(settings['probes'])); report_path = output_dir/names[0]
        with tempfile.TemporaryDirectory(prefix='openfigura-skin-probe-') as folder:
            cfg = Path(folder)/'config.json'
            cfg.write_text(json.dumps({'model': str(model), 'output_dir': str(output_dir), 'params': settings}), encoding='utf-8')
            argv = [binary, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                    str(Path(__file__).with_name('skin_probe_worker.py')), '--', str(cfg)]
            start = time.monotonic()
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
            ledger = base.CommandResult(argv, proc.returncode, round(time.monotonic()-start, 2),
                                        (proc.stdout or '')[-4000:], (proc.stderr or '')[-4000:]).ledger()
        report = None
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            ledger['stderr_tail'] += f'\nMissing or invalid skin probe report: {exc}'
        source_unchanged = model.is_file() and hashlib.sha256(model.read_bytes()).hexdigest() == source_sha
        produced = source_unchanged and proc.returncode == 0 and report_complete(report, settings) and report['source_sha256'] == source_sha and all(
            (output_dir/name).is_file() and (output_dir/name).stat().st_size > 0 for name in names)
        if not produced and ledger['exit_code'] == 0:
            ledger['exit_code'] = 1
            ledger['stderr_tail'] += '\nBlender did not complete skin probe report and required artifacts'
        return {'backend': self.id, **ledger, 'status': 'pass' if produced else 'fail', 'produced': produced,
                'report_path': str(report_path), 'report': report,
                'source_unchanged': source_unchanged, 'files': [name for name in names if (output_dir/name).is_file()]}
