import ast
import math
from pathlib import Path

import pytest

from openfigura.backends.mesh_tools import MeshToolsBackend


def helpers():
    worker = Path(__file__).parents[1] / 'src/openfigura/backends/mesh_tools_worker.py'
    functions = [n for n in ast.parse(worker.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in {'uv_triangle_metrics', 'require_uv_quality'}]
    assert len(functions) == 2, 'UV area and quality gates are required before publishing an atlas'
    ns = {'math': math}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(worker), 'exec'), ns)
    return ns


def test_reports_sparse_uv_area_and_rejects_collapsed_atlas():
    ns = helpers()
    metrics = ns['uv_triangle_metrics']([[(.2,.2),(.200001,.2),(.2,.200001)]], 1024)
    assert metrics['summed_uv_area'] < 1e-10
    assert metrics['sub_half_texel_triangles'] == 1
    with pytest.raises(ValueError, match='sparse'):
        ns['require_uv_quality'](metrics)


def test_rejects_degenerate_and_nonfinite_uv_without_omitting_triangles():
    ns = helpers()
    for triangle in [[(0,0),(0,0),(1,1)], [(0,0),(1,0),(0,float('nan'))]]:
        metrics = ns['uv_triangle_metrics']([triangle], 1024)
        assert metrics['triangles'] == 1
        with pytest.raises(ValueError):
            ns['require_uv_quality'](metrics)


def test_valid_uv_statistics_do_not_claim_overlap_or_art_approval():
    ns = helpers()
    metrics = ns['uv_triangle_metrics']([[(0,0),(1,0),(0,1)]], 1024)
    ns['require_uv_quality'](metrics)
    assert metrics['summed_uv_area'] == .5
    assert metrics['degenerate_uv_triangles'] == 0
    assert metrics['sub_half_texel_triangles'] == 0


@pytest.mark.parametrize('params', [{'resolution':True},{'resolution':1000},{'margin_pixels':-1},{'margin_pixels':float('nan')},{'margin_pixels':True},{'mode':'hidden-faces'}])
def test_invalid_uv_settings_rejected_before_subprocess(tmp_path, monkeypatch, params):
    source=tmp_path/'source.glb';source.write_bytes(b'fixture')
    monkeypatch.setattr(MeshToolsBackend,'binary',lambda self:None)
    with pytest.raises(ValueError):
        MeshToolsBackend().process(source,tmp_path/'out.glb','uv',params)
