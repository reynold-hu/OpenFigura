"""Task-local durable stage records, with atomic claims and verified reuse.

This records explicit caller decisions. It does not schedule workers or infer
whether a stage should run, and never writes the task's provenance ledger.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .contracts import AssetRef
from .task import Task


def _canonical(value: Any) -> str:
    def validate(item: Any) -> None:
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                validate(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                validate(child)
            return
        raise ValueError('parameters must contain finite JSON values with string keys')
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False)


class Workflow:
    """A reopenable workflow database scoped to an existing task directory."""

    def __init__(self, taskroot: Path):
        self.root = Path(taskroot).resolve(strict=True)
        task = Task.open(self.root)
        if (not isinstance(task.id, str) or not task.id.strip()
                or not isinstance(task.entries, list)
                or type(task.created_utc) not in (int, float)
                or not math.isfinite(task.created_utc)):
            raise ValueError('invalid task provenance')
        self.task_id = task.id
        self.database = self.root / 'workflow.sqlite3'
        if self.database.is_symlink():
            raise ValueError('workflow database must not be a symlink')
        with self._transaction(initializing=True) as connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('unsupported workflow schema version')
            if version == 0:
                connection.execute('CREATE TABLE stages (stage_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
                connection.execute('CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, stage_id TEXT NOT NULL, payload TEXT NOT NULL)')
                connection.execute('CREATE TABLE metadata (task_id TEXT NOT NULL)')
                connection.execute('INSERT INTO metadata VALUES (?)', (self.task_id,))
                connection.execute('PRAGMA user_version = 1')
            stored_task = connection.execute('SELECT task_id FROM metadata').fetchone()
            if stored_task != (self.task_id,):
                raise ValueError('workflow task identity does not match provenance')

    @contextmanager
    def _transaction(self, initializing: bool = False):
        connection = sqlite3.connect(self.database, timeout=30)
        try:
            connection.execute('BEGIN IMMEDIATE')
            if not initializing and connection.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('unsupported workflow schema version')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _refs(self, refs: list[AssetRef]) -> list[dict]:
        if not isinstance(refs, list) or any(not isinstance(ref, AssetRef) for ref in refs):
            raise ValueError('assets must be a list of AssetRef objects')
        for ref in refs:
            ref.verify(self.root)
        return [ref.to_dict() for ref in refs]

    @staticmethod
    def _load(connection, stage_id: str) -> dict:
        row = connection.execute('SELECT payload FROM stages WHERE stage_id = ?', (stage_id,)).fetchone()
        if row is None:
            raise ValueError(f'unknown stage: {stage_id}')
        return json.loads(row[0])

    @staticmethod
    def _save(connection, stage: dict) -> dict:
        payload = _canonical(stage)
        connection.execute('INSERT OR REPLACE INTO stages VALUES (?, ?)', (stage['stage_id'], payload))
        connection.execute('INSERT INTO events (stage_id, payload) VALUES (?, ?)', (stage['stage_id'], payload))
        return json.loads(payload)

    def _verify_serialized(self, refs: list[dict]) -> None:
        self._refs([AssetRef.from_dict(ref) for ref in refs])

    def _cached(self, connection, key: str) -> dict | None:
        rows = connection.execute('SELECT payload FROM stages ORDER BY rowid DESC').fetchall()
        for row in rows:
            stage = json.loads(row[0])
            if stage['cache_key'] != key or stage['status'] != 'pass' or not stage['outputs']:
                continue
            try:
                self._verify_serialized(stage['inputs'])
                self._verify_serialized(stage['outputs'])
            except (ValueError, OSError):
                continue
            return stage
        return None

    def submit(self, step: str, inputs: list[AssetRef], params: dict,
               backend: str, backend_version: str) -> dict:
        for name, value in (('step', step), ('backend', backend), ('backend_version', backend_version)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{name} must be a nonempty string')
        if type(params) is not dict:
            raise ValueError('params must be a dictionary')
        copied_params = json.loads(_canonical(params))
        refs = self._refs(inputs)
        key = hashlib.sha256(_canonical({'step': step, 'inputs': refs, 'params': copied_params,
                                       'backend': backend, 'backend_version': backend_version}).encode()).hexdigest()
        with self._transaction() as connection:
            self._verify_serialized(refs)
            cached = self._cached(connection, key)
            stage = {'schema_version': 1, 'stage_id': uuid.uuid4().hex, 'task_id': self.task_id,
                     'step': step, 'inputs': refs, 'params': copied_params, 'backend': backend,
                     'backend_version': backend_version, 'cache_key': key,
                     'status': 'pass' if cached else 'queued', 'attempt': 1,
                     'outputs': cached['outputs'] if cached else [],
                     'cached_from': cached['stage_id'] if cached else None,
                     'resumed_from': None, 'reason': None, 'updated_utc': time.time()}
            return self._save(connection, stage)

    def claim(self, stage_id: str) -> dict:
        with self._transaction() as connection:
            stage = self._load(connection, stage_id)
            if stage['status'] != 'queued':
                raise ValueError('only a queued stage can be claimed')
            self._verify_serialized(stage['inputs'])
            stage.update(status='running', updated_utc=time.time())
            return self._save(connection, stage)

    def complete(self, stage_id: str, outputs: list[AssetRef]) -> dict:
        with self._transaction() as connection:
            stage = self._load(connection, stage_id)
            if stage['status'] != 'running':
                raise ValueError('only a running stage can complete')
            if not outputs:
                raise ValueError('completion requires verified outputs')
            self._verify_serialized(stage['inputs'])
            refs = self._refs(outputs)
            input_paths = {(self.root / ref['task_relative_path']).resolve() for ref in stage['inputs']}
            for ref in outputs:
                path = (self.root / ref.task_relative_path).resolve()
                if path in input_paths or any(path.samefile(input_path) for input_path in input_paths):
                    raise ValueError('an input path cannot be reused as an output')
                if ('rejected' in Path(ref.task_relative_path).parts
                        or 'rejected' in path.relative_to(self.root).parts):
                    raise ValueError('rejected assets cannot be outputs')
                if ref.producer_step != stage['step']:
                    raise ValueError('output producer_step must match stage step')
            stage.update(status='pass', outputs=refs, updated_utc=time.time())
            return self._save(connection, stage)

    def fail(self, stage_id: str, reason: str) -> dict:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('failure reason must be a nonempty string')
        with self._transaction() as connection:
            stage = self._load(connection, stage_id)
            if stage['status'] != 'running':
                raise ValueError('only a running stage can fail')
            stage.update(status='fail', reason=reason, updated_utc=time.time())
            return self._save(connection, stage)

    def cancel(self, stage_id: str) -> dict:
        with self._transaction() as connection:
            stage = self._load(connection, stage_id)
            if stage['status'] != 'queued':
                raise ValueError('only queued stages can cancel; running workers require cooperative cancellation')
            stage.update(status='cancelled', updated_utc=time.time())
            return self._save(connection, stage)

    def resume(self, stage_id: str) -> dict:
        with self._transaction() as connection:
            prior = self._load(connection, stage_id)
            if prior['status'] not in ('fail', 'cancelled', 'blocked'):
                raise ValueError('only failed, cancelled or blocked stages can resume')
            stage = {**prior, 'stage_id': uuid.uuid4().hex, 'status': 'queued',
                     'attempt': prior['attempt'] + 1, 'resumed_from': prior['stage_id'],
                     'cached_from': None, 'reason': None, 'outputs': [], 'updated_utc': time.time()}
            return self._save(connection, stage)

    def status(self, stage_id: str | None = None) -> dict:
        with self._transaction() as connection:
            if stage_id is not None:
                return self._load(connection, stage_id)
            return {'schema_version': 1, 'task_id': self.task_id, 'stages': [json.loads(row[0]) for row in
                    connection.execute('SELECT payload FROM stages ORDER BY rowid').fetchall()]}

    def events(self, stage_id: str) -> list[dict]:
        with self._transaction() as connection:
            self._load(connection, stage_id)
            return [{'sequence': sequence, **json.loads(payload)} for sequence, payload in connection.execute(
                'SELECT sequence, payload FROM events WHERE stage_id = ? ORDER BY sequence', (stage_id,)).fetchall()]
