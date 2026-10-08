from openfigura.core import engine


def test_builtin_execution_identity_changes_when_implementation_bytes_change(monkeypatch):
    monkeypatch.setattr(engine, 'sha256_file', lambda path: 'a' * 64)
    first = engine._backend_version('export-snapshot')
    monkeypatch.setattr(engine, 'sha256_file', lambda path: 'b' * 64)
    assert engine._backend_version('export-snapshot') != first


def test_composite_execution_identity_includes_gate_and_export_workers(monkeypatch):
    changed = set()
    monkeypatch.setattr(engine, 'sha256_file', lambda p: 'b' * 64 if p.name in changed else 'a' * 64)
    first = engine._backend_version('unimate')
    changed.add('contact.py')
    assert engine._backend_version('unimate') != first
    first = engine._backend_version('export-snapshot')
    changed.add('format_export_worker.py')
    assert engine._backend_version('export-snapshot') != first
