"""Backend registry: pluggable generation/rendering tools with honest
capability reporting. A backend that cannot run here must say so — silence
counts as unsupported, and no step may claim a result it did not produce.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class Backend(Protocol):
    id: str
    kind: str  # "generate" | "render" | "postprocess"

    def capabilities(self) -> "Capabilities": ...


@dataclass
class Capabilities:
    available: bool
    hardware: str = ""          # "metal", "cuda", "cpu", ...
    reason: str = ""            # why unavailable, verbatim from the probe
    notes: dict[str, str] = field(default_factory=dict)


@dataclass
class Registration:
    factory: Callable[[], Backend]
    description: str = ""


_REGISTRY: dict[str, Registration] = {}


def register(backend_id: str, factory: Callable[[], Backend], description: str = "") -> None:
    _REGISTRY[backend_id] = Registration(factory, description)


def available() -> dict[str, str]:
    return {bid: reg.description for bid, reg in sorted(_REGISTRY.items())}


def get(backend_id: str) -> Backend:
    reg = _REGISTRY.get(backend_id)
    if reg is None:
        raise KeyError(f"unknown backend {backend_id!r}; known: {sorted(_REGISTRY)}")
    return reg.factory()


def probe(backend_id: str) -> Capabilities:
    return get(backend_id).capabilities()


def _bootstrap() -> None:
    """Register built-in backends lazily so import errors stay per-backend."""
    from openfigura.backends import pixal3d, blender, photo_paint  # noqa: F401


_bootstrap()
