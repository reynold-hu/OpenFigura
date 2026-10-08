from types import SimpleNamespace
import pytest
np=pytest.importorskip('numpy')
from openfigura.backends.mesh_sampling import seed_sampling

def test_same_seed_restarts_one_stream_without_repeating_each_draw():
    module=SimpleNamespace(sample=SimpleNamespace(sample_surface=lambda n,seed=None:np.random.default_rng(seed).random(n)))
    seed_sampling(module,42);a=module.sample.sample_surface(10);b=module.sample.sample_surface(10)
    assert not np.array_equal(a,b)
    seed_sampling(module,42)
    assert np.array_equal(a,module.sample.sample_surface(10))
    assert np.array_equal(b,module.sample.sample_surface(10))

def test_explicit_caller_seed_is_preserved():
    module=SimpleNamespace(sample=SimpleNamespace(sample_surface=lambda n,seed=None:np.random.default_rng(seed).random(n)))
    seed_sampling(module,42)
    assert np.array_equal(module.sample.sample_surface(10,seed=7),np.random.default_rng(7).random(10))
