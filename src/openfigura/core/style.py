"""Pixel style requirements; these do not assert temporal consistency."""
from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Any

from .contracts import contract_data


@dataclass(frozen=True)
class StyleSpec:
    canvas_width: int
    canvas_height: int
    pixel_scale: int
    palette: tuple[str, ...]
    outline_policy: str
    shading_policy: str
    fps: int
    anchor: str
    transparent_background: bool

    def __post_init__(self) -> None:
        for name, maximum in (('canvas_width', 4096), ('canvas_height', 4096),
                              ('pixel_scale', 16), ('fps', 120)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f'{name} must be an integer from 1 to {maximum}')
        if not isinstance(self.palette, (tuple, list)) or not 1 <= len(self.palette) <= 256:
            raise ValueError('palette must contain 1 to 256 RGB hex colors')
        for color in self.palette:
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('palette colors must use #RRGGBB')
        colors = tuple(color.upper() for color in self.palette)
        if len(set(colors)) != len(colors):
            raise ValueError('palette colors must be unique')
        object.__setattr__(self, 'palette', colors)
        for name, choices in (('outline_policy', ('none', 'single_pixel')),
                              ('shading_policy', ('flat', 'stepped')),
                              ('anchor', ('feet', 'center'))):
            if getattr(self, name) not in choices:
                raise ValueError(f'unsupported {name}')
        if type(self.transparent_background) is not bool:
            raise ValueError('transparent_background must be a boolean')

    def to_dict(self) -> dict[str, Any]:
        data = {field.name: getattr(self, field.name) for field in fields(self)}
        data['palette'] = list(self.palette)
        return {'schema_version': 1, **data}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StyleSpec:
        return cls(**contract_data(cls, data))
