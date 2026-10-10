import numpy as np
import pytest

from openfigura.backends.expression_field import (
    load_obj_positions, dense_deltas, nearest_map, sample_field, compose)


class FakeTarget:
    def __init__(self, name, indices, deltas):
        self.name, self.indices, self.deltas = name, tuple(indices), tuple(deltas)


def test_load_obj_positions(tmp_path):
    obj = tmp_path / 'm.obj'
    obj.write_text('# comment\nv 0 0 0\nv 1 2 3\nvn 0 0 1\nf 1 2 2\n')
    positions = load_obj_positions(obj)
    assert positions.shape == (2, 3)
    assert positions[1].tolist() == [1.0, 2.0, 3.0]
    empty = tmp_path / 'e.obj'
    empty.write_text('# nothing\n')
    with pytest.raises(ValueError):
        load_obj_positions(empty)


def test_dense_deltas_bounds_and_layout():
    target = FakeTarget('jaw', [0, 2], [[0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
    field = dense_deltas(target, 4)
    assert field.shape == (4, 3)
    assert field[0].tolist() == [0.0, 0.0, -1.0]
    assert field[1].tolist() == [0.0, 0.0, 0.0]
    assert field[3].tolist() == [0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match='beyond base mesh'):
        dense_deltas(FakeTarget('x', [9], [[0, 0, 0]]), 4)


def test_nearest_map_and_sample_falloff():
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    dense = np.array([[0, 0, 1], [0, 0, 0], [0, 0, 0]], dtype=float)
    character = np.array([[0, 0, 0], [0.5, 0, 0]], dtype=float)
    mapping = nearest_map(base, character)
    field = sample_field(dense, mapping)
    assert field[0].tolist() == [0, 0, 1]
    assert 0 < field[1][2] < 1  # decayed, same direction
    far = nearest_map(base, np.array([[50.0, 0, 0]]))
    assert sample_field(dense, far)[0].tolist() == pytest.approx([0, 0, 0], abs=1e-9)


def test_compose_weights_and_validates():
    fields = {'a': np.array([[1.0, 0, 0]]), 'b': np.array([[0, 1.0, 0]])}
    result = compose(fields, {'a': 2.0, 'b': 0.5}, intensity=0.5)
    assert result[0].tolist() == [1.0, 0.25, 0.0]
    with pytest.raises(ValueError):
        compose({}, {'a': 1})
