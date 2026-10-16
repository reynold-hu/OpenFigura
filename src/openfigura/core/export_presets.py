"""Named FBX export orientations (domain table, no backend imports).

An FBX file carries its own up/front axes and unit numbers; whether a target
engine accepts it without visible rotation or size error is decided by that
engine's importer. This table maps engine names to the exporter arguments that
author the convention the engine documents, so the ledger records a resolved
orientation instead of whoever toggled a dropdown last.

Measured 2026-10-16 on Blender 5.2.2, Godot 4.7.2 (evidence:
``.local/runs/2026-10-16-borrow-batch/``, marker probe + bunny AABB):

- ``blender``: exporter defaults (``bake_space_transform=False``). File keeps
  Blender-native geometry with axis metadata; Blender re-import is identity.
- ``godot``: ``bake_space_transform=True`` with the Y-up pair. Baking rotates
  the geometry into Y-up and multiplies numbers by 100 (FBX declares 1 unit =
  1 cm), so Godot's cm-to-meter import lands on the exact GLB-control AABB.
  Without the bake, Godot imported the raw Z-up layout 100x too small.
- ``unity``: same authoring as godot; Unity's FBX unit conversion is the
  documented reason, import not verified on this host.
- ``unreal``: ``bake_space_transform=True`` with Z-up/X-forward per UE's
  documented coordinate system and centimeters; import not verified on this
  host (axis metadata verified; Blender manual-axis round trip identity).
"""
from __future__ import annotations

FBX_PRESETS: dict[str, dict] = {
    'blender': {
        'axis_forward': '-Z',
        'axis_up': 'Y',
        'bake_space_transform': False,
        'target': 'Blender (Y-up, -Z forward importer defaults)',
        'note': 'exporter defaults; Blender-native geometry with axis metadata; metadata import round-trip verified on Blender 5.2.2',
        'verified': 'blender-round-trip-2026-10-16',
    },
    'godot': {
        'axis_forward': '-Z',
        'axis_up': 'Y',
        'bake_space_transform': True,
        'target': 'Godot 4 (Y-up, -Z forward)',
        'note': 'baked Y-up authoring lands on the GLB-control AABB in Godot 4.7.2; unbaked export was 100x small',
        'verified': 'godot-import-2026-10-16',
    },
    'unity': {
        'axis_forward': '-Z',
        'axis_up': 'Y',
        'bake_space_transform': True,
        'target': 'Unity (Y-up; FBX cm converted to meters on import)',
        'note': 'baked Y-up authoring per Unity FBX unit conversion; import not verified on this host',
        'verified': 'convention-only',
    },
    'unreal': {
        'axis_forward': 'X',
        'axis_up': 'Z',
        'bake_space_transform': True,
        'target': 'Unreal Engine (Z-up, X-forward; centimeter units)',
        'note': 'baked Z-up/X-forward authoring; UE import not verified on this host',
        'verified': 'convention-only',
    },
}
