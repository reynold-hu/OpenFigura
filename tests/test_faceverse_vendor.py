"""Test source provenance; optional geometry smoke uses upstream code verbatim."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'src/openfigura/_vendor/faceverse_v4'

def test_faceverse_import_hashes_match_recorded_upstream_or_explicit_patch():
    source=json.loads((ROOT/'third_party/faceverse-v4/SOURCE.json').read_text())
    assert source['commit']=='19c67cc4d7234b1ea7d55a185a2cb55fd49bb877'
    modified=[]
    for f in source['files']:
        digest=hashlib.sha256((VENDOR/f['path']).read_bytes()).hexdigest()
        assert digest==f['vendored_sha256']
        if f['modified']:modified.append(f['path'])
        else:assert digest==f['upstream_sha256']
    assert modified==['faceversev4/__init__.py']

def test_faceverse_subtraction_keeps_licenses_and_no_models_or_binary():
    for name in ['LICENSE','LICENSE_3DDFAV2','LICENSE_Deep3DFaceRecon_pytorch']:
        assert (VENDOR/name).is_file()
    assert not (VENDOR/'run.py').exists() and not (VENDOR/'example').exists()
    assert not any(p.suffix in {'.pyd','.pth','.npy','.onnx'} for p in VENDOR.rglob('*') if p.is_file())

def test_cpu_decoder_does_not_eagerly_require_network_or_opencv():
    text=(VENDOR/'faceversev4/__init__.py').read_text()
    assert 'from .FaceVerseModel_torch import FaceVerseModel_torch' in text
    assert 'from .FaceVerse_networks import FaceVerseRecon' not in text
