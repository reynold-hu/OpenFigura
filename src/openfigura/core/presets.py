"""Use-case presets: advisory defaults for mesh budgets, with stated bases.

A use case is how the produced asset will be consumed (game runtime, offline
animation, print, headset, product viewer, or unstated). It exists so the
agent and the CLI resolve the *same* face budgets instead of each run choosing
ad hoc numbers, and so the ledger can say which default came from where.

Honesty rules for this table:

- Only ``retopo_target_faces`` is encoded, because that is the budget this
  codebase can actually apply (``mesh retopo`` passes it to QuadriFlow after
  the watertight remesh; ``mesh optimize`` derives ``ratio = target / current``
  from the GLB's own triangle count, computed, not guessed).
- ``basis`` names where each number comes from. Vendor-derived numbers say so
  and are marked ``vendor-claim``; OpenFigura recommendations say
  ``openfigura-recommendation`` and are not measurements.
- No preset may silently skip a step: ``None`` means "no implicit budget",
  not "use something reasonable".
"""
from __future__ import annotations

USE_CASES: dict[str, dict] = {
    'game': {
        'retopo_target_faces': 20_000,
        'basis': 'openfigura-recommendation',
        'note': 'real-time engines commonly ship 10k-50k triangles per hero asset; not measured here',
    },
    'animation': {
        'retopo_target_faces': 50_000,
        'basis': 'vendor-claim',
        'note': 'matches the published Tripo P1.0/P2.0 budget of <=50,000 triangles (Tripo Studio bundle 2026-10-16)',
    },
    'print': {
        'retopo_target_faces': None,
        'basis': 'openfigura-recommendation',
        'note': 'no implicit decimation: print fidelity prefers source detail; run optimize explicitly if the print service needs a cap',
    },
    'vr_ar': {
        'retopo_target_faces': 20_000,
        'basis': 'openfigura-recommendation',
        'note': 'mobile-headset budgets are tighter than desktop; not measured here',
    },
    'product_display': {
        'retopo_target_faces': 80_000,
        'basis': 'openfigura-recommendation',
        'note': 'web/product viewers tolerate more geometry than runtime engines; not measured here',
    },
    'general': {
        'retopo_target_faces': None,
        'basis': 'openfigura-recommendation',
        'note': 'unstated use case: no implicit budget',
    },
}

PRESET_OPERATIONS = ('retopo', 'optimize')
