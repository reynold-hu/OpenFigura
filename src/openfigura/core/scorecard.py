"""Preliminary asset readiness scorecard — deterministic, no aesthetics.

This answers "how far is this asset from a reviewable delivery?" for an agent:
evidence completeness, structural integrity, input quality, topology and
delivery state. It deliberately does **not** score beauty, face likeness or
material appeal; those stay with the human rubric
(`docs/2026-10-17-face-quality-rubric.md`) and `visual_approval`.

Scores are 0-100 with transparent formulas. No model, GPU or network is used.
"""
from __future__ import annotations

from pathlib import Path

from . import preflight as _preflight
from .inspect import inspect_glb
from .printability import check_printability
from .task import Task, sha256_file

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
WEIGHTS = {"structure": 0.30, "evidence": 0.25, "input": 0.20,
           "printability": 0.15, "delivery": 0.10}
PRINT_WEIGHTS = {"structure": 0.25, "evidence": 0.20, "input": 0.10,
                 "printability": 0.35, "delivery": 0.10}
PROFILES = {"default": WEIGHTS, "print": PRINT_WEIGHTS}


def _clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _input_image(task: Task) -> Path | None:
    folder = task.root / "input"
    if not folder.is_dir():
        return None
    preferred = folder / "input.png"
    if preferred.is_file():
        return preferred
    candidates = sorted(p for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
                        and "mask" not in p.stem.lower() and "roi" not in p.stem.lower())
    return candidates[0] if candidates else None


def _structure(inspected: dict, printable: dict) -> int:
    score = 100.0
    if not inspected.get("ok"):
        score -= 40
    if not inspected.get("has_normals"):
        score -= 15
    if not inspected.get("has_uv"):
        score -= 15
    if not inspected.get("materials_with_pbr"):
        score -= 10
    stats = printable["stats"]
    score -= min(20, stats["degenerate_faces"] * 2)
    score -= min(10, stats["duplicate_faces"])
    return _clamp(score)


def _printability(printable: dict) -> int:
    score = 100.0
    stats = printable["stats"]
    score -= min(50, stats["boundary_edges"])
    score -= min(50, stats["nonmanifold_edges"])
    score -= min(20, stats["degenerate_faces"] * 2)
    if stats.get("fits_build_volume") is False:
        score -= 25
    return _clamp(score)


def _input_quality(report: dict | None) -> int | None:
    if report is None:
        return None
    score = 100.0
    if not report.get("ok"):
        score -= 40
    score -= min(40, 10 * len(report.get("warnings", [])))
    symmetry = report.get("symmetry", {})
    if symmetry.get("status") == "measured":
        if symmetry.get("label") == "asymmetric":
            score -= 25
        elif symmetry.get("label") == "roughly-symmetric":
            score -= 10
    face = report.get("face", {})
    if face.get("status") == "measured":
        estimated = face.get("estimated_face_px_at_1024")
        if isinstance(estimated, (int, float)):
            if estimated < 64:
                score -= 20
            elif estimated < 128:
                score -= 10
        if face.get("touches_border"):
            score -= 10
    return _clamp(score)


def _evidence(task: Task, input_image: Path | None) -> tuple[int, dict]:
    steps = [entry.get("step") for entry in task.entries]
    present = set(steps)
    last_inspect_ok = any(entry.get("step") == "inspect" and entry.get("ok")
                          for entry in task.entries)
    frames = len(list((task.root / "render").rglob("*.png"))) if (task.root / "render").is_dir() else 0
    components = {
        "input": 15 if input_image is not None else 0,
        "preflight": 15 if "preflight" in present else 0,
        "generate": 25 if "generate" in present else 0,
        "inspect": 20 if last_inspect_ok else 0,
        "render": 15 if frames else 0,
        "export": 10 if "export" in present else 0,
    }
    return _clamp(sum(components.values())), {
        "components": components,
        "ledger_steps": sorted({str(step) for step in steps if step}),
        "render_frames": frames,
    }


def _delivery(task: Task) -> tuple[int, dict]:
    exports = [entry for entry in task.entries if entry.get("step") == "export"]
    provenance = (task.root / "provenance.json").is_file()
    hashed = bool(exports and (exports[-1].get("glb_sha256") or exports[-1].get("primary")))
    score = (60 if exports else 0) + (20 if provenance else 0) + (20 if hashed else 0)
    return _clamp(score), {"exports": len(exports), "provenance": provenance,
                           "export_has_hash": hashed}


def scorecard(task: Task, params: dict | None = None, artifact: str = "model.glb") -> dict:
    params = dict(params or {})
    unknown = set(params) - {"face", "build_volume_mm", "profile"}
    if unknown:
        raise ValueError(f"unknown score parameter(s): {sorted(unknown)}")
    face = params.get("face", False)
    if type(face) is not bool:
        raise ValueError("face must be a boolean")
    profile = params.get("profile", "default")
    if profile not in PROFILES:
        raise ValueError(f"unknown score profile {profile!r}; known: {sorted(PROFILES)}")
    build_volume = params.get("build_volume_mm")
    model = task.artifact(artifact)
    if not model.is_file():
        raise FileNotFoundError("nothing to score; run generate first")

    inspected = inspect_glb(model)
    printable = check_printability(model, build_volume_mm=build_volume)
    input_image = _input_image(task)
    report = _preflight.preflight(input_image, face=face) if input_image else None

    subscores = {
        "structure": _structure(inspected, printable),
        "printability": _printability(printable),
        "input": _input_quality(report),
        "evidence": None,
        "delivery": None,
    }
    evidence_score, evidence_meta = _evidence(task, input_image)
    delivery_score, delivery_meta = _delivery(task)
    subscores["evidence"] = evidence_score
    subscores["delivery"] = delivery_score
    weights = PROFILES[profile]
    available = {name: value for name, value in subscores.items()
                 if isinstance(value, int) and name in weights}
    total_weight = sum(weights[name] for name in available)
    overall = _clamp(sum(weights[name] * value for name, value in available.items()) / total_weight) \
        if total_weight else 0
    verdict = ("ready_for_human_review"
               if overall >= 80 and subscores["structure"] >= 80 and evidence_score >= 80
               else "needs_work")
    return {
        "verdict": verdict,
        "overall": overall,
        "profile": profile,
        "weights": weights,
        "subscores": subscores,
        "metrics": {
            "artifact": artifact,
            "input_sha256": sha256_file(model),
            "triangles": inspected["triangles"],
            "has_normals": inspected["has_normals"],
            "has_uv": inspected["has_uv"],
            "materials_with_pbr": inspected["materials_with_pbr"],
            "printability": printable["stats"],
            "bbox": printable.get("bbox"),
            "input_image": str(input_image.relative_to(task.root)) if input_image else None,
            "preflight": None if report is None else {
                "ok": report["ok"], "errors": report["errors"],
                "warnings": report["warnings"], "symmetry": report["symmetry"],
                "face": report.get("face"),
            },
            "evidence": evidence_meta,
            "delivery": delivery_meta,
        },
        "human_review": {"status": "pending",
                         "note": "aesthetics, face likeness and material appeal are not scored here",
                         "rubric": "docs/2026-10-17-face-quality-rubric.md"},
        "limitations": [
            "Deterministic readiness only; this is not a visual quality verdict.",
            "Printability is reported for every asset; it matters most for profile='print'.",
            "Scores reflect the recorded task evidence, not unrecorded manual work.",
        ],
    }
