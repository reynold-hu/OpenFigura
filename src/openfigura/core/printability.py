"""Local printability report from an embedded GLB (standard library only).

Answers a narrow question: does this mesh *look* printable at the topology and
size level? It counts open and non-manifold edges, degenerate and duplicate
faces, connected shells, and checks a caller-supplied build volume. It does not
measure wall thickness, overhang angle, self-intersections or orientation, and
it never repairs anything.

Scope and honest limits:

- Indexed and non-indexed triangle primitives with FLOAT VEC3 positions and
  embedded buffers are read. All primitives are welded by exact float positions
  before topology counting (glTF splits vertices for normal/UV seams, so raw
  index topology would report false boundaries); positions that differ by one
  ULP stay separate.
- Degenerate faces mean exact zero area (repeated or collinear vertices at
  float precision), not a tuned epsilon.
- Node transforms are not applied; a non-identity transform is reported as a
  warning so bounds are read as local coordinates. Skinned/morph assets are
  checked in their rest geometry only.
- Compressed, external-buffer, sparse and non-triangle primitives are counted
  as unsupported and make the report fail closed rather than pass silently.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
INDEX_TYPES = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = Path(path).read_bytes()
    if len(data) < 12:
        raise ValueError("file too small to be a GLB")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC or version != 2:
        raise ValueError("not a glTF 2.0 binary container")
    if length != len(data):
        raise ValueError("GLB length field does not match file size")
    offset = 12
    doc = None
    blob = b""
    chunks = []
    while offset + 8 <= len(data):
        size, kind = struct.unpack_from("<II", data, offset)
        if offset + 8 + size > len(data):
            raise ValueError("truncated GLB chunk")
        if kind == CHUNK_JSON:
            doc = json.loads(data[offset + 8:offset + 8 + size].decode("utf-8"))
        elif kind == CHUNK_BIN:
            blob = data[offset + 8:offset + 8 + size]
        chunks.append(kind)
        offset += 8 + size
    if doc is None:
        raise ValueError("no JSON chunk found")
    if chunks.count(CHUNK_BIN) != 1:
        raise ValueError("expected exactly one BIN chunk")
    buffers = doc.get("buffers", [])
    if len(buffers) != 1 or buffers[0].get("uri"):
        raise ValueError("one embedded buffer is required")
    if int(buffers[0].get("byteLength", -1)) > len(blob):
        raise ValueError("buffer byteLength exceeds BIN chunk")
    return doc, blob


def _view_bytes(doc: dict, blob: bytes, view_index: int) -> tuple[int, int, int]:
    view = doc["bufferViews"][view_index]
    if view.get("buffer", 0) != 0:
        raise ValueError("external buffers are unsupported")
    if "EXT_meshopt_compression" in view.get("extensions", {}):
        raise ValueError("meshopt compression is unsupported")
    offset = int(view.get("byteOffset", 0))
    length = int(view["byteLength"])
    stride = int(view.get("byteStride", 0))
    if offset < 0 or length < 0 or offset + length > len(blob):
        raise ValueError("bufferView outside BIN chunk")
    return offset, length, stride


def _positions(doc: dict, blob: bytes, accessor_index: int) -> list[tuple[float, float, float]]:
    accessor = doc["accessors"][accessor_index]
    if accessor.get("type") != "VEC3" or accessor.get("componentType") != 5126:
        raise ValueError("POSITION must be FLOAT VEC3")
    if "sparse" in accessor:
        raise ValueError("sparse POSITION accessors are unsupported")
    count = int(accessor.get("count", 0))
    if count <= 0:
        raise ValueError("POSITION accessor is empty")
    offset, length, stride = _view_bytes(doc, blob, int(accessor["bufferView"]))
    stride = stride or 12
    if stride < 12:
        raise ValueError("POSITION byteStride below 12")
    start = offset + int(accessor.get("byteOffset", 0))
    if start + (count - 1) * stride + 12 > offset + length:
        raise ValueError("POSITION accessor outside bufferView")
    values = []
    for i in range(count):
        values.append(struct.unpack_from("<fff", blob, start + i * stride))
    return values


def _indices(doc: dict, blob: bytes, accessor_index: int, vertex_count: int) -> list[int]:
    accessor = doc["accessors"][accessor_index]
    if accessor.get("type") != "SCALAR" or "sparse" in accessor:
        raise ValueError("index accessor must be a nonsparse scalar")
    code, size = INDEX_TYPES.get(accessor.get("componentType"), (None, 0))
    if code is None:
        raise ValueError("unsupported index component type")
    count = int(accessor.get("count", 0))
    if count <= 0 or count % 3:
        raise ValueError("index count must be a positive multiple of 3")
    offset, length, stride = _view_bytes(doc, blob, int(accessor["bufferView"]))
    stride = stride or size
    if stride < size:
        raise ValueError("index byteStride below component size")
    start = offset + int(accessor.get("byteOffset", 0))
    if start + (count - 1) * stride + size > offset + length:
        raise ValueError("index accessor outside bufferView")
    values = []
    for i in range(count):
        value = struct.unpack_from("<" + code, blob, start + i * stride)[0]
        if value >= vertex_count:
            raise ValueError("triangle index outside POSITION")
        values.append(value)
    return values


def _weld(positions: list[tuple[float, float, float]]):
    """Return (mapping, unique_positions) welding exact float positions."""
    seen: dict[tuple[float, float, float], int] = {}
    unique: list[tuple[float, float, float]] = []
    mapping = []
    for position in positions:
        key = (float(position[0]), float(position[1]), float(position[2]))
        index = seen.get(key)
        if index is None:
            index = len(unique)
            seen[key] = index
            unique.append(key)
        mapping.append(index)
    return mapping, unique


def _identity_node(node: dict) -> bool:
    if "matrix" in node and node["matrix"] != [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]:
        return False
    if any(abs(float(v)) > 0 for v in node.get("translation", [])):
        return False
    if "rotation" in node and node["rotation"] != [0, 0, 0, 1]:
        return False
    if "scale" in node and node["scale"] != [1, 1, 1]:
        return False
    return True


def _component_count(parent: list[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def check_printability(path: Path, build_volume_mm=None) -> dict:
    if build_volume_mm is not None:
        if (not isinstance(build_volume_mm, (list, tuple)) or len(build_volume_mm) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                       for v in build_volume_mm)):
            raise ValueError("build_volume_mm must be three positive finite numbers")

    doc, blob = _read_glb(Path(path))
    errors: list[str] = []
    warnings: list[str] = []
    unsupported: list[str] = []
    stats = {
        "meshes": len(doc.get("meshes", [])),
        "primitives": 0, "checked_primitives": 0,
        "vertices": 0, "raw_vertices": 0, "triangles": 0,
        "boundary_edges": 0, "nonmanifold_edges": 0,
        "degenerate_faces": 0, "duplicate_faces": 0,
        "shells": 0, "closed_primitives": 0,
        "nonindexed_primitives": 0,
    }
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    transforms_ignored = False
    skinned = bool(doc.get("skins"))
    morph = False

    for node in doc.get("nodes", []):
        if node.get("mesh") is not None and not _identity_node(node):
            transforms_ignored = True

    for mesh in doc.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            stats["primitives"] += 1
            label = f"primitive {stats['primitives'] - 1}"
            if primitive.get("mode", 4) != 4:
                unsupported.append(f"{label}: mode {primitive.get('mode')} is not triangles")
                continue
            if "KHR_draco_mesh_compression" in primitive.get("extensions", {}):
                unsupported.append(f"{label}: Draco compression is unsupported")
                continue
            if primitive.get("targets"):
                morph = True
            attributes = primitive.get("attributes", {})
            if "POSITION" not in attributes:
                unsupported.append(f"{label}: no POSITION attribute")
                continue
            try:
                positions = _positions(doc, blob, int(attributes["POSITION"]))
                raw_vertices = len(positions)
                if primitive.get("indices") is None:
                    stats["nonindexed_primitives"] += 1
                    if len(positions) % 3:
                        raise ValueError("non-indexed vertex count is not a multiple of 3")
                    triangles, positions = _weld(positions)
                else:
                    triangles = _indices(doc, blob, int(primitive["indices"]), len(positions))
                    mapping, positions = _weld(positions)
                    triangles = [mapping[i] for i in triangles]
                vertices = len(positions)
            except (KeyError, IndexError, ValueError, struct.error) as exc:
                unsupported.append(f"{label}: {exc}")
                continue

            stats["checked_primitives"] += 1
            stats["vertices"] += vertices
            stats["raw_vertices"] += raw_vertices
            tri_count = len(triangles) // 3
            stats["triangles"] += tri_count
            for position in positions:
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], position[axis])
                    maximum[axis] = max(maximum[axis], position[axis])

            edges: dict[tuple[int, int], int] = {}
            faces_seen: set[tuple[int, int, int]] = set()
            degenerate = 0
            duplicates = 0
            parent = list(range(vertices))
            used = [False] * vertices
            for face in range(tri_count):
                a, b, c = triangles[face * 3:face * 3 + 3]
                if a == b or b == c or a == c:
                    degenerate += 1
                    continue
                pa, pb, pc = positions[a], positions[b], positions[c]
                ab = (pb[0]-pa[0], pb[1]-pa[1], pb[2]-pa[2])
                ac = (pc[0]-pa[0], pc[1]-pa[1], pc[2]-pa[2])
                cross = (ab[1]*ac[2]-ab[2]*ac[1],
                         ab[2]*ac[0]-ab[0]*ac[2],
                         ab[0]*ac[1]-ab[1]*ac[0])
                if cross == (0.0, 0.0, 0.0):
                    degenerate += 1
                    continue
                key = tuple(sorted((a, b, c)))
                if key in faces_seen:
                    duplicates += 1
                else:
                    faces_seen.add(key)
                for u, v in ((a, b), (b, c), (c, a)):
                    edge = (u, v) if u < v else (v, u)
                    edges[edge] = edges.get(edge, 0) + 1
                for u, v in ((a, b), (b, c), (c, a)):
                    ru, rv = _component_count(parent, u), _component_count(parent, v)
                    if ru != rv:
                        parent[rv] = ru
                used[a] = used[b] = used[c] = True

            boundary = sum(1 for count in edges.values() if count == 1)
            nonmanifold = sum(1 for count in edges.values() if count > 2)
            shells = len({_component_count(parent, i) for i, flag in enumerate(used) if flag})
            stats["boundary_edges"] += boundary
            stats["nonmanifold_edges"] += nonmanifold
            stats["degenerate_faces"] += degenerate
            stats["duplicate_faces"] += duplicates
            stats["shells"] += shells
            if boundary == 0 and nonmanifold == 0 and degenerate == 0 and tri_count > 0:
                stats["closed_primitives"] += 1

    if stats["triangles"] == 0 and not unsupported:
        errors.append("no triangle geometry found")
    if unsupported:
        errors.append(f"{len(unsupported)} unsupported primitive(s); coverage is incomplete")
    if stats["boundary_edges"]:
        errors.append(f"{stats['boundary_edges']} open boundary edge(s): the mesh is not watertight")
    if stats["nonmanifold_edges"]:
        errors.append(f"{stats['nonmanifold_edges']} non-manifold edge(s): more than two faces share an edge")
    if stats["degenerate_faces"]:
        errors.append(f"{stats['degenerate_faces']} degenerate face(s) with exactly zero area")
    if stats["duplicate_faces"]:
        warnings.append(f"{stats['duplicate_faces']} duplicate face(s) by vertex indices")
    if stats["shells"] > 1:
        warnings.append(f"{stats['shells']} disconnected shells: verify assembly or merge intent")
    if stats["triangles"] > 1_000_000:
        warnings.append(f"{stats['triangles']} triangles: expect slow slicing; consider retopo/optimize")
    if transforms_ignored:
        warnings.append("node transforms are not applied: bounds and orientation are local coordinates")
    if skinned or morph:
        warnings.append("skinned/morph asset: checked in rest geometry only; deformation is not evaluated")

    bbox = None
    if minimum[0] is not math.inf:
        size = [maximum[i] - minimum[i] for i in range(3)]
        bbox = {
            "min": [round(minimum[i], 9) for i in range(3)],
            "max": [round(maximum[i], 9) for i in range(3)],
            "size_m": [round(v, 9) for v in size],
        }
    fits = None
    if build_volume_mm is not None and bbox is not None:
        size_mm = [v * 1000.0 for v in bbox["size_m"]]
        fits = all(size_mm[i] <= float(build_volume_mm[i]) for i in range(3))
        stats["build_volume_mm"] = [float(v) for v in build_volume_mm]
        stats["size_mm"] = [round(v, 6) for v in size_mm]
        stats["fits_build_volume"] = fits
        if not fits:
            overflow = [f"axis {axis}: {size_mm[axis]:.1f}mm > {build_volume_mm[axis]}mm"
                        for axis in range(3) if size_mm[axis] > build_volume_mm[axis]]
            warnings.append("does not fit the build volume: " + "; ".join(overflow))

    return {
        "ok": not errors,
        "status": "pass" if not errors else "fail",
        "stats": stats,
        "bbox": bbox,
        "errors": errors,
        "warnings": warnings,
        "unsupported": unsupported,
        "unchecked": ["wall_thickness", "overhang_angle", "self_intersections", "orientation"],
        "limitations": [
            "Topology and size only; wall thickness, overhang and self-intersections are not measured.",
            "Degenerate means exactly zero area at float precision, not a tuned epsilon.",
            "All primitives are welded by exact float positions before topology counting; normal/UV seam splits are merged.",
            "Node transforms are not applied; a non-identity transform is reported as a warning.",
        ],
    }
