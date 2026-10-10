import hashlib
from pathlib import Path

import pytest

from openfigura.backends.makehuman_targets import (
    parse_target_text, load_pack, coverage, PACK_SHA256, Target)

RUNTIME = Path.home() / 'Desktop/Local/Opensource/OpenFigura-runtimes/makehuman-expressions'
FACEUNITS = RUNTIME / 'faceunits01.zip'


def test_parse_target_text_basic():
    indices, deltas = parse_target_text('31 0 0 -.001\n32 0 0 -.001\n\n33 -.001 0 0\n')
    assert indices == (31, 32, 33)
    assert deltas == ((0.0, 0.0, -0.001), (0.0, 0.0, -0.001), (-0.001, 0.0, 0.0))


def test_parse_target_text_rejects_malformed():
    for bad in ['', '1 2 3', 'x 0 0 0', '5 0 0 nan', '1 0 0 0\n1 0 0 1', '-1 0 0 0']:
        with pytest.raises(ValueError):
            parse_target_text(bad)


@pytest.mark.skipif(not FACEUNITS.is_file(), reason='CC0 faceunits pack not fetched')
def test_load_faceunits_pack_and_licenses():
    targets = load_pack(FACEUNITS, PACK_SHA256['faceunits01'])
    assert 'cheekPuff' in targets and 'eyeLookDownLeft' in targets
    assert len(targets) >= 50
    assert all(t.license.upper() == 'CC0' for t in targets.values())
    assert targets['cheekPuff'].max_abs > 0
    with pytest.raises(ValueError, match='hash mismatch'):
        load_pack(FACEUNITS, 'deadbeef')


@pytest.mark.skipif(not FACEUNITS.is_file(), reason='CC0 faceunits pack not fetched')
def test_coverage_against_mediapipe_channels():
    targets = load_pack(FACEUNITS, PACK_SHA256['faceunits01'])
    channels = ['jawOpen', 'eyeBlinkLeft', 'mouthSmileRight', 'cheekPuff',
                'browDownLeft', 'nonexistentChannel']
    result = coverage(channels, targets)
    assert result['matched'] >= 5
    assert 'nonexistentChannel' in result['missing_targets']
    assert result['non_cc0_targets'] == []


def test_coverage_reports_unused_targets():
    targets = {'a': Target('a', 'CC0', (0,), ((0.0, 0.0, 0.1),)),
               'b': Target('b', 'CC0', (1,), ((0.0, 0.1, 0.0),))}
    result = coverage(['a'], targets)
    assert result['matched'] == 1 and result['missing_targets'] == []
    assert result['unused_targets'] == ['b']
