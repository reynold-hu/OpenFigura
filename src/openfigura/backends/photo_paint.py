"""Optional CPU source projection; no neural weights and no upload."""
from __future__ import annotations
import importlib.util
import json
import math
import time
from pathlib import Path
from openfigura.core import registry
from openfigura.core.registry import Capabilities

class PhotoPaintBackend:
    id = 'photo-paint'
    kind = 'postprocess'

    def capabilities(self):
        missing = [m for m in ('numpy', 'PIL') if importlib.util.find_spec(m) is None]
        return Capabilities(not missing, hardware='cpu',
            reason=('install openfigura[detail]: missing '+', '.join(missing)) if missing else '',
            notes={'license':'Apache-2.0','scope':'BaseColor only; geometry unchanged'})

    def refine(self, model: Path, views: Path, output: Path,
               mask: Path | None = None, strength: float = 1.0) -> dict:
        import numpy as np
        from PIL import Image
        from openfigura._vendor import photo_paint as pp
        start = time.monotonic()
        original = model.read_bytes()
        positions, uvs, faces, texture = pp.read_glb(model)
        if not all(np.isfinite(a).all() for a in (positions, uvs)):
            raise ValueError('nonfinite mesh coordinates')
        doc, binary = pp._split_glb(original)
        if doc['meshes'][0]['primitives'][0].get('mode',4) != 4:
            raise ValueError('triangle meshes required')
        if len(faces)==0 or faces.min()<0 or faces.max()>=len(positions):
            raise ValueError('invalid triangle indices')
        refs, scale = pp.load_views(views)
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError('mesh_scale must be finite and positive')
        masked = []
        for view in refs:
            if not 0 < view.fov_x < math.pi or not np.isfinite(view.fov_x):
                raise ValueError('invalid reference FOV')
            matrix = view.cam_to_world
            if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1]):
                raise ValueError('invalid reference camera matrix')
            rotation=matrix[:3,:3]
            if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-4) or not np.isclose(np.linalg.det(rotation),1,atol=1e-4):
                raise ValueError('reference cameras must be rigid right-handed transforms')
            alpha=view.image[...,3]
            if np.all(alpha==255) or not np.any(alpha>0):
                raise ValueError('reference needs a real foreground alpha matte')
            if mask:
                roi=Image.open(mask).convert('L')
                if roi.size!=(view.image.shape[1],view.image.shape[0]):
                    raise ValueError('ROI mask must match every reference frame size')
                image=view.image.copy()
                image[...,3]=np.rint(image[...,3].astype(float)*np.asarray(roi)/255).astype('uint8')
                view=pp.View(image,matrix,view.fov_x,view.name)
            masked.append(view)
        painted, weight = pp.paint_texture(texture,positions,uvs,faces,masked,scale,
                                            settings=pp.Settings(match_colour=False))
        painted=np.rint(texture.astype(float)*(1-strength)+painted.astype(float)*strength).astype('uint8')
        result=pp.replace_base_colour(original,pp.encode_png(painted))
        newdoc,newbin=pp._split_glb(result)
        target=doc['images'][pp.base_colour_image_index(doc)]['bufferView']
        for i,(a,b) in enumerate(zip(doc['bufferViews'],newdoc['bufferViews'])):
            if i==target:continue
            if binary[a.get('byteOffset',0):a.get('byteOffset',0)+a['byteLength']]!=newbin[b.get('byteOffset',0):b.get('byteOffset',0)+b['byteLength']]:
                raise RuntimeError('refinement changed a protected mesh/material buffer')
        output.write_bytes(result)
        Image.fromarray(np.rint(weight*strength*255).astype('uint8')).save(output.with_suffix('.trust.png'))
        return {'produced':True,'exit_code':0,'wall_seconds':round(time.monotonic()-start,2),
                'operation':'image-to-3dlab source projection','geometry_unchanged':True,
                'non_basecolor_buffers_identical':True,'triangles':len(faces),
                'fraction_atlas_trust_gt_half':float((weight*strength>.5).mean()),
                'trust_map':output.with_suffix('.trust.png').name,
                'limitations':['source lighting remains in RGB','unseen surfaces are not reconstructed','no geometry repair'],
                'upstream_commit':'10e007b1998c5ffed0b09e16d4218c05a1803afb'}

    def head_roi(self, model: Path, views: Path, output: Path,
                 head_fraction: float = 0.18, expand: float = 0.08) -> dict:
        """Project the model's head band into the single reference view and
        write its convex silhouette as an ROI mask — for characters whose
        stylized faces defeat landmark detectors."""
        import numpy as np
        from PIL import Image
        from openfigura._vendor import photo_paint as pp
        from openfigura.backends.face_align import convex_hull
        if not 0.05 <= head_fraction <= 0.5:
            raise ValueError('head_fraction must be in 0.05..0.5')
        if not 0.0 <= expand <= 0.5:
            raise ValueError('expand must be in 0..0.5')
        positions, _uvs, _faces, _texture = pp.read_glb(model)
        refs, scale = pp.load_views(views)
        if len(refs) != 1:
            raise ValueError(f'head ROI needs exactly one reference view; got {len(refs)}')
        view = refs[0]
        z = positions[:, 2]
        band = positions[z >= z.max() - head_fraction * (z.max() - z.min())]
        if len(band) < 10:
            raise ValueError('head band too sparse to project')
        x, y, depth = pp.project(pp.to_view_space(band, mesh_scale=scale), view)
        front = depth > 1e-9
        if int(front.sum()) < 10:
            raise ValueError('head band projects in front of the camera in no part')
        hull = convex_hull(zip(x[front], y[front]))
        height, width = view.image.shape[:2]
        cx = sum(p[0] for p in hull) / len(hull)
        cy = sum(p[1] for p in hull) / len(hull)
        factor = 1.0 + expand
        polygon = [(min(max(cx + (px - cx) * factor, 0), width - 1),
                    min(max(cy + (py - cy) * factor, 0), height - 1)) for px, py in hull]
        from openfigura.backends.face_align import FaceAlignBackend
        coverage = FaceAlignBackend().draw_mask(polygon, width, height, output)
        return {'produced': True, 'view': view.name, 'image_size': [int(width), int(height)],
                'head_band_vertices': int(front.sum()), 'hull_points': len(polygon),
                'coverage': round(coverage, 4), 'geometry_unchanged': True}


registry.register('photo-paint',PhotoPaintBackend,'visible source pixels -> BaseColor; optional CPU extra')
