"""Optional CPU source projection; no neural weights and no upload."""
from __future__ import annotations
import importlib.util
import json
import math
import time
from pathlib import Path
from openfigura.core import registry
from openfigura.core.registry import Capabilities

class PhotoPaintBackend:
    id = 'photo-paint'
    kind = 'postprocess'

    def capabilities(self):
        missing = [m for m in ('numpy', 'PIL') if importlib.util.find_spec(m) is None]
        return Capabilities(not missing, hardware='cpu',
            reason=('install openfigura[detail]: missing '+', '.join(missing)) if missing else '',
            notes={'license':'Apache-2.0','scope':'BaseColor only; geometry unchanged'})

    def refine(self, model: Path, views: Path, output: Path,
               mask: Path | None = None, strength: float = 1.0) -> dict:
        import numpy as np
        from PIL import Image
        from openfigura._vendor import photo_paint as pp
        start = time.monotonic()
        original = model.read_bytes()
        positions, uvs, faces, texture = pp.read_glb(model)
        if not all(np.isfinite(a).all() for a in (positions, uvs)):
            raise ValueError('nonfinite mesh coordinates')
        doc, binary = pp._split_glb(original)
        if doc['meshes'][0]['primitives'][0].get('mode',4) != 4:
            raise ValueError('triangle meshes required')
        if len(faces)==0 or faces.min()<0 or faces.max()>=len(positions):
            raise ValueError('invalid triangle indices')
        refs, scale = pp.load_views(views)
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError('mesh_scale must be finite and positive')
        masked = []
        for view in refs:
            if not 0 < view.fov_x < math.pi or not np.isfinite(view.fov_x):
                raise ValueError('invalid reference FOV')
            matrix = view.cam_to_world
            if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1]):
                raise ValueError('invalid reference camera matrix')
            rotation=matrix[:3,:3]
            if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-4) or not np.isclose(np.linalg.det(rotation),1,atol=1e-4):
                raise ValueError('reference cameras must be rigid right-handed transforms')
            alpha=view.image[...,3]
            if np.all(alpha==255) or not np.any(alpha>0):
                raise ValueError('reference needs a real foreground alpha matte')
            if mask:
                roi=Image.open(mask).convert('L')
                if roi.size!=(view.image.shape[1],view.image.shape[0]):
                    raise ValueError('ROI mask must match every reference frame size')
                image=view.image.copy()
                image[...,3]=np.rint(image[...,3].astype(float)*np.asarray(roi)/255).astype('uint8')
                view=pp.View(image,matrix,view.fov_x,view.name)
            masked.append(view)
        painted, weight = pp.paint_texture(texture,positions,uvs,faces,masked,scale,
                                            settings=pp.Settings(match_colour=False))
        painted=np.rint(texture.astype(float)*(1-strength)+painted.astype(float)*strength).astype('uint8')
        result=pp.replace_base_colour(original,pp.encode_png(painted))
        newdoc,newbin=pp._split_glb(result)
        target=doc['images'][pp.base_colour_image_index(doc)]['bufferView']
        for i,(a,b) in enumerate(zip(doc['bufferViews'],newdoc['bufferViews'])):
            if i==target:continue
            if binary[a.get('byteOffset',0):a.get('byteOffset',0)+a['byteLength']]!=newbin[b.get('byteOffset',0):b.get('byteOffset',0)+b['byteLength']]:
                raise RuntimeError('refinement changed a protected mesh/material buffer')
        output.write_bytes(result)
        Image.fromarray(np.rint(weight*strength*255).astype('uint8')).save(output.with_suffix('.trust.png'))
        return {'produced':True,'exit_code':0,'wall_seconds':round(time.monotonic()-start,2),
                'operation':'image-to-3dlab source projection','geometry_unchanged':True,
                'non_basecolor_buffers_identical':True,'triangles':len(faces),
                'fraction_atlas_trust_gt_half':float((weight*strength>.5).mean()),
                'trust_map':output.with_suffix('.trust.png').name,
                'limitations':['source lighting remains in RGB','unseen surfaces are not reconstructed','no geometry repair'],
                'upstream_commit':'10e007b1998c5ffed0b09e16d4218c05a1803afb'}

registry.register('photo-paint',PhotoPaintBackend,'visible source pixels -> BaseColor; optional CPU extra')
