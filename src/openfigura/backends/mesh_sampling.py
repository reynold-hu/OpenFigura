"""Seed the modern trimesh sampling API inside the dedicated ML subprocess."""
def seed_sampling(trimesh_module, seed):
    import numpy as np
    current=trimesh_module.sample.sample_surface
    original=getattr(current,'_openfigura_original',current)
    generator=np.random.default_rng(seed)
    def sample_surface(*args,**kwargs):
        if kwargs.get('seed') is None:kwargs['seed']=generator
        return original(*args,**kwargs)
    sample_surface._openfigura_original=original
    trimesh_module.sample.sample_surface=sample_surface
