# Asset and workflow foundation

These experimental interfaces validate project style and persist explicit stage
requests. They do not execute a workflow automatically. Existing generate,
autorig and retarget commands continue to run through their existing engine paths.

## Pixel style

Save a JSON specification such as:

```json
{
  "schema_version": 1,
  "canvas_width": 64,
  "canvas_height": 64,
  "pixel_scale": 1,
  "palette": ["#000000", "#FFFFFF", "#593C39", "#D99573"],
  "outline_policy": "single_pixel",
  "shading_policy": "flat",
  "fps": 8,
  "anchor": "feet",
  "transparent_background": true
}
```

```sh
openfigura set-style TASK --spec style.json
openfigura project-style TASK
```

MCP mirrors: `figura_set_style(task_root, spec)` and
`figura_project_style(task_root)`. The same engine validates both. Each style
revision is preserved in provenance, palette colours are canonical uppercase
RGB hex, and visual approval stays pending. Setting these fields does not render,
pixelize, apply outlines, animate, or guarantee a consistent art style.

## Hash-linked assets

An immutable `AssetRef` stores `task_relative_path`, SHA-256, asset kind and
producer step. Verification checks the actual file and rejects traversal,
symlink escapes, non-files and changed content. References remain valid after
moving the entire task, provided the referenced bytes are unchanged.

## Durable stage requests

Save a request JSON containing all five fields:

```json
{
  "step": "generate",
  "inputs": [],
  "params": {"seed": 42},
  "backend": "pixal3d",
  "backend_version": "user-recorded-runtime-version"
}
```

This example illustrates the request schema. An execution worker must supply
the actual staged input references and discover the actual runtime version;
empty inputs and a user-written version are not evidence of a generation run.

```sh
openfigura workflow-submit TASK --spec request.json
openfigura workflow-status TASK
openfigura workflow-cancel TASK STAGE_ID
openfigura workflow-resume TASK STAGE_ID
```

MCP mirrors are `figura_workflow_submit`, `figura_workflow_status`,
`figura_workflow_cancel`, and `figura_workflow_resume` with the same engine results.
Submission records a request; no model starts. No timer marks a stage successful.

`workflow.sqlite3` stores stage snapshots and append-only transition events using
SQLite transactions. The existing `provenance.json` still stores backend commands
and style revisions. Keep both when moving or archiving tasks. This is a stage
state store, not a complete scheduler or dependency graph.

Internal worker APIs atomically claim queued stages, verify all input references,
and accept nonempty outputs only after hash checking, producer validation and
rejected-folder checks. Outputs cannot alias inputs, including hardlinks. Two
independent clients cannot both claim the same stage. Passing stages may be reused
within the same task only if parameters, backend version and file hashes match.

Queued stages can be cancelled. Running stages refuse cancellation because
cooperative backend termination is not implemented yet. Failed or cancelled
stages resume as new attempts, retaining old events. A running stage left by a
process crash remains running; automatic crash recovery and ownership leases are
future work. Never resume an active model merely because a client timed out.

## Export verification

The existing GLB exporter now inspects current bytes on every export and checks
the SHA-256 of a saved inspection report. A stale report cannot approve a changed
asset. This check does not yet require every imported GLB to originate from a
passing workflow stage; full workflow-managed export evidence is a separate
integration task. Regional contact or aesthetic quality cannot be inferred from
structural inspection alone.

Export inspection and publication use a private GLB snapshot and verify the copied
hash before publishing its normal delivery name. Ledger writers reload the latest
record under a cross-process file lock and replace complete JSON atomically;
independent clients cannot overwrite each other's revisions. POSIX locking has
been tested on this Mac; the Windows msvcrt branch still needs runtime validation.

## Scope and verification

No new neural runtime or image library is required by these core contracts.
The tests cover relocation, bad paths and hashes, palette bounds, state transitions,
separate-client claims, cache invalidation, retries and real MCP tool invocation
when its optional extra is installed. Bare-core tests skip the MCP integration.

GPU resource leases, automatic stage dispatch, dependency graph, pixel generation,
topology/baking, HTTP service, workbench and remote worker protocols remain planned.
Source decisions are in `2026-10-08-ecosystem-deep-review.md`.
