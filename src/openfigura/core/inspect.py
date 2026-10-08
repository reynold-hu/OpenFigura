"""GLB structural inspection with the standard library only.

Parses the glTF binary container (12-byte header + JSON/BIN chunks) and
reports meshes, primitives, accessors and image/PBR references. This is an
integrity check, not a quality check — quality is judged from renders.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

GLB_MAGIC = 0x46546C67  # "glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def gltf_document(path: Path) -> dict:
    """Parse a GLB container and return its JSON chunk (stdlib only)."""
    data = Path(path).read_bytes()
    if len(data) < 12:
        raise ValueError("file too small to be a GLB")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError(f"bad GLB magic 0x{magic:08x}")
    off = 12
    gltf = None
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        payload = data[off + 8: off + 8 + clen]
        if ctype == CHUNK_JSON:
            gltf = json.loads(payload.decode("utf-8"))
        off += 8 + clen
    if gltf is None:
        raise ValueError("no JSON chunk found")
    return gltf


def inspect_glb(path: Path) -> dict:
    gltf = gltf_document(path)
    data = Path(path).read_bytes()
    version = struct.unpack_from("<I", data, 4)[0]
    length = struct.unpack_from("<I", data, 8)[0]
    off = 12
    bin_size = 0
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        if ctype == CHUNK_BIN:
            bin_size = clen
        off += 8 + clen

    meshes = gltf.get("meshes", [])
    primitives = [p for m in meshes for p in m.get("primitives", [])]
    attrs = {a for p in primitives for a in p.get("attributes", {})}
    materials = gltf.get("materials", [])
    pbr = [m for m in materials if "pbrMetallicRoughness" in m]

    def tex_ref(mat, key):
        tex = mat.get("pbrMetallicRoughness", {}).get(key) or mat.get(key) or {}
        idx = tex.get("index")
        if idx is None:
            return None
        src = gltf["textures"][idx].get("source")
        return gltf["images"][src].get("name", f"image{src}") if src is not None else None

    accessors = gltf.get("accessors", [])

    def prim_triangles(p: dict) -> int:
        idx = p.get("indices")
        if idx is None or idx >= len(accessors):
            return 0
        count = accessors[idx].get("count", 0)
        return count // 3 if count % 3 == 0 else 0

    report = {
        "glb_version": version,
        "total_bytes": length,
        "bin_bytes": bin_size,
        "meshes": len(meshes),
        "primitives": len(primitives),
        "triangles": sum(prim_triangles(p) for p in primitives),
        "vertex_attributes": sorted(attrs),
        "materials": len(materials),
        "materials_with_pbr": len(pbr),
        "base_color_textures": [tex_ref(m, "baseColorTexture") for m in materials],
        "metal_rough_textures": [tex_ref(m, "metallicRoughnessTexture") for m in materials],
        "skins": len(gltf.get("skins", [])),
        "joint_count": sum(len(s.get("joints", [])) for s in gltf.get("skins", [])),
        "animation_clips": [a.get("name", f"clip{i}") for i, a in enumerate(gltf.get("animations", []))],
        "has_skinning": bool(gltf.get("skins")) and {"JOINTS_0", "WEIGHTS_0"}.issubset(attrs),
        "has_normals": "NORMAL" in attrs,
        "has_uv": any(a.startswith("TEXCOORD") for a in attrs),
    }
    problems = []
    if not report["meshes"]:
        problems.append("no meshes")
    if not report["has_normals"]:
        problems.append("missing NORMAL attribute")
    if not report["has_uv"]:
        problems.append("missing TEXCOORD attribute")
    if report["primitives"] and not report["materials_with_pbr"]:
        problems.append("primitives present but no PBR material")
    report["problems"] = problems
    report["ok"] = not problems
    return report
