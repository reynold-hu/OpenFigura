"""Final evaluation report: readiness scorecard + optional external validators.

The report is the human handoff artifact: it states what was measured, what was
unavailable and why, and what still requires a human decision. It never scores
aesthetics; the rubric remains the only aesthetic gate.
"""
from __future__ import annotations

from pathlib import Path

from . import external_validation
from .scorecard import scorecard
from .task import Task, sha256_file


def _validated(external: dict, name: str) -> dict:
    return external.get(name, {"status": "skipped"})


def _markdown(task: Task, evaluation: dict) -> str:
    score = evaluation["scorecard"]
    metrics = score["metrics"]
    printable = metrics["printability"]
    preflight = metrics["preflight"]
    external = evaluation["external"]
    lines = [
        f"# Evaluation report — `{task.id}`",
        "",
        f"- artifact: `{evaluation['artifact']}`",
        f"- sha256: `{evaluation['input_sha256']}`",
        f"- verdict: **{score['verdict']}** · overall **{score['overall']}/100** "
        f"(profile `{score['profile']}`)",
        f"- readiness only: {score['human_review']['note']}",
        "",
        "## Sub-scores",
        "",
        "| sub-score | value |",
        "|---|---|",
    ]
    for name, value in score["subscores"].items():
        lines.append(f"| {name} | {'—' if value is None else value} |")
    lines += [
        "",
        "## Structure and topology",
        "",
        f"- triangles: {metrics['triangles']}",
        f"- normals / UV / PBR: {metrics['has_normals']} / {metrics['has_uv']} / {metrics['materials_with_pbr']}",
        f"- boundary edges: {printable['boundary_edges']}",
        f"- non-manifold edges: {printable['nonmanifold_edges']}",
        f"- degenerate faces: {printable['degenerate_faces']}",
        f"- duplicate faces: {printable['duplicate_faces']}",
        f"- connected shells: {printable['shells']}",
    ]
    if metrics.get("bbox"):
        lines.append(f"- bbox size (m): {metrics['bbox']['size_m']}")
    if "fits_build_volume" in printable:
        lines.append(f"- fits build volume: {printable['fits_build_volume']}")
    orientation = printable.get("orientation")
    if orientation:
        lines += [
            f"- overhang area: {orientation['overhang_area_mm2']} mm² "
            f"({orientation['overhang_area_ratio'] * 100:.1f}% of surface, "
            f"threshold {orientation['overhang_angle_deg']}°)",
            f"- bed-contact area: {orientation['bed_contact_area_mm2']} mm² "
            f"(tolerance {orientation['bed_tolerance_mm']} mm)",
        ]
    lines += ["", "## Input preflight", ""]
    if preflight is None:
        lines.append("- unavailable: no input image in the task")
    else:
        lines.append(f"- ok: {preflight['ok']}")
        for error in preflight["errors"]:
            lines.append(f"- error: {error}")
        for warning in preflight["warnings"]:
            lines.append(f"- warning: {warning}")
        symmetry = preflight.get("symmetry") or {}
        lines.append(f"- symmetry: {symmetry.get('status')} {symmetry.get('label') or ''}".rstrip())
        face = preflight.get("face") or {}
        lines.append(f"- face: {face.get('status')} "
                     f"(estimated px at 1024: {face.get('estimated_face_px_at_1024')})")
    lines += ["", "## External validation", ""]
    gltf = _validated(external, "gltf_validator")
    lines.append(f"### glTF-Validator — {gltf['status']}")
    if gltf["status"] == "validated":
        if gltf.get("validator_version"):
            lines.append(f"- version: {gltf['validator_version']}")
        issues = gltf.get("issues", {})
        lines.append(f"- errors/warnings/infos/hints: {issues.get('numErrors', 0)} / "
                     f"{issues.get('numWarnings', 0)} / {issues.get('numInfos', 0)} / "
                     f"{issues.get('numHints', 0)}")
        for message in (issues.get("messages") or [])[:10]:
            lines.append(f"- [{message.get('severity')}] {message.get('code')}: "
                         f"{message.get('message')} @ {message.get('pointer')}")
    else:
        lines.append(f"- {gltf.get('reason', 'not run')}")
    trimesh = _validated(external, "trimesh")
    lines.append(f"### trimesh — {trimesh['status']}")
    if trimesh["status"] == "validated":
        for key in ("vertices", "faces", "degenerate_faces", "is_watertight",
                    "is_winding_consistent", "is_volume", "components",
                    "euler_number", "area_m2", "volume_m3", "extents_m"):
            lines.append(f"- {key}: {trimesh.get(key)}")
    else:
        lines.append(f"- {trimesh.get('reason', 'not run')}")
    lines += ["", "## Evidence coverage", ""]
    evidence = metrics["evidence"]
    lines.append(f"- ledger steps: {', '.join(evidence['ledger_steps']) or '—'}")
    lines.append(f"- components: {evidence['components']}")
    lines.append(f"- render frames: {evidence['render_frames']}")
    delivery = metrics["delivery"]
    lines.append(f"- export entries: {delivery['exports']} · provenance: {delivery['provenance']}")
    lines += ["", "## Human handoff (pending)", ""]
    for item in evaluation["human_handoff"]["checklist"]:
        lines.append(f"- [ ] {item}")
    renders = sorted(p.relative_to(task.root).as_posix()
                     for p in (task.root / "render").rglob("*.png")) \
        if (task.root / "render").is_dir() else []
    lines.append("")
    lines.append("Renders to review: " + (", ".join(f"`{p}`" for p in renders) or "none"))
    lines += ["", "## Limitations", ""]
    for limitation in evaluation["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def build(task: Task, params: dict | None = None,
          artifact: str = "model.glb") -> tuple[dict, str]:
    params = dict(params or {})
    external = params.pop("external", True)
    if type(external) is not bool:
        raise ValueError("external must be a boolean")
    score = scorecard(task, params, artifact)
    model = task.artifact(artifact)
    expected = sha256_file(model)
    results = {"gltf_validator": {"status": "skipped"}, "trimesh": {"status": "skipped"}}
    if external:
        results["gltf_validator"] = external_validation.gltf_validator(model)
        results["trimesh"] = external_validation.trimesh_check(model)
        if sha256_file(model) != expected:
            raise RuntimeError("asset changed during external validation")
    evaluation = {
        "schema_version": 1,
        "artifact": artifact,
        "input_sha256": expected,
        "scorecard": score,
        "external": results,
        "human_handoff": {
            "status": "pending",
            "checklist": [
                "If this is a character asset, open the renders and score the "
                "five-dimension face rubric (docs/2026-10-17-face-quality-rubric.md).",
                "Record visual approval or rejection; the agent cannot self-approve.",
                "Confirm print orientation and build volume if this asset is for printing.",
                "Confirm license and usage fit for the intended product.",
            ],
            "rubric": "docs/2026-10-17-face-quality-rubric.md",
        },
        "limitations": [
            "Deterministic readiness only; aesthetics and face likeness are not scored.",
            "External validators run only when their runtimes are configured; "
            "unavailable means not measured, not passed.",
            "glTF-Validator findings describe spec conformance, not artistic quality.",
            "trimesh metrics describe geometry at load time; transforms and scene "
            "semantics may differ in the target engine.",
        ],
    }
    return evaluation, _markdown(task, evaluation)
