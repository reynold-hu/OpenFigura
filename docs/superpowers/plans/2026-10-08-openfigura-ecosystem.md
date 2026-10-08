# OpenFigura 3D／2D 资产生态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 CLI、MCP 和核心任务记录一致的前提下，把 OpenFigura 扩展为可验证的 3D 主链、2D 像素流水线、可选本地工作台和第三方后端生态。

**Architecture:** 继续使用无模型依赖的 `core` 任务引擎作为唯一事实源。算法以后端能力注册；工作流通过阶段输入输出、缓存键、设备声明和质量门连接；CLI、MCP、IDE 和外部 Agent 只调用核心。3D 与 2D 共享项目风格规范、资产引用和 provenance，但分别保留几何／动作证据与像素／切帧证据。

**Tech Stack:** Python 3.10+ 标准库核心、pytest；Blender／Godot 后端；可选 NumPy/Pillow；MCP；后续本地 React/Vite 工作台；外部 ComfyUI、Pixal3D、TRELLIS、Hunyuan、MIA、SkinTokens、MocapAnything 等仅通过适配器接入。

---

## Scope and delivery order

### 2026-10-08 源码复核后的执行说明

首批已开发并验证：资产／风格契约、Task 记录方法、CLI/MCP 风格入口、
SQLite 阶段状态及原子领取、同任务缓存、重跑记录、CLI/MCP 阶段接口。
兼容已存在的后端工具；还没有注册完整 DAG 或自动启动计算进程。
导出已经改为检查并发布私有快照，保存过的检查哈希不匹配则拒绝。
审查发现的缓存输出别名、并发历史覆盖和检查／导出竞态均有先失败后通过的回归测试。
Task 2 的 registry capability 扩展、资源闸门及后续任务保持未完成状态。
进度证据见 `docs/PROGRESS.md`；第一批说明见 `docs/asset-workflow-foundation.md`。

本文件原先属于跨子系统实施概要，不是包含完整代码的逐步施工图。
本轮先落地 Task 1 和 Task 2 的持久状态基础，以及共用 CLI/MCP 风格入口。
Task 2 使用标准库 SQLite 事务保存阶段／事件，已有后端 `provenance.json` 保持兼容；
不直接让多个进程覆写 JSON。未接入的 GPU 调度、工作台、拓扑烘焙和像素处理不标记完成。
Task 1 的实际测试合并于 `tests/test_asset_contracts.py`；字段使用 canvas_width/height。
基础风格设置仅校验参数，不执行描边或阴影，不产生像素资源。
后续逐批补充施工图和实际验收，源码与一手资料见 `docs/2026-10-08-ecosystem-deep-review.md`。

本计划拆成三个可独立交付的子项目，每个子项目都有自己的测试、证据和提交：

1. **核心工作流与 3D 主链**：先把阶段状态、缓存、资源闸门和现有 3D 后端统一起来。
2. **2D 像素流水线**：在稳定的 3D 渲染输出上建立像素化、风格规范和 sprite sheet 导出，同时支持直接 2D 输入。
3. **工作台与生态接入**：最后提供只读／调度型 IDE 页面、外部 Agent 接口和社区组件兼容性报告。

第一阶段不把未经真实硬件验证的 SkinTokens、MocapAnything 或 Kimodo 标记为可用；它们只能以 `experimental` 后端出现。

## Task 1: Version the shared asset and style contracts

**Files:**
- Create: `src/openfigura/core/contracts.py`
- Create: `src/openfigura/core/style.py`
- Modify: `src/openfigura/core/task.py`
- Modify: `src/openfigura/core/engine.py`
- Test: `tests/test_contracts.py`
- Test: `tests/test_style.py`

- [ ] **Step 1: Write failing contract tests**

  Add tests that construct a style contract with `canvas_width=64`, `canvas_height=64`, `pixel_scale=1`, a six-colour palette, `outline_policy="single_pixel"`, `fps=8`, and `anchor="feet"`; assert JSON round-trip preserves values and rejects a non-integer canvas, empty palette, zero FPS, and unknown policy. Add an asset reference test that rejects a missing file hash and accepts a relative task artifact plus SHA-256.

- [ ] **Step 2: Run the focused tests**

  Run:

  ```sh
  .venv/bin/python -m pytest tests/test_contracts.py tests/test_style.py -q
  ```

  Expected: FAIL because the contract classes do not exist.

- [ ] **Step 3: Implement immutable contracts**

  Define `StyleSpec` with validated fields `canvas_width`, `canvas_height`, `pixel_scale`, `palette`, `outline_policy`, `shading_policy`, `fps`, `anchor`, and `transparent_background`. Define `AssetRef` with `task_relative_path`, `sha256`, `kind`, and `producer_step`. Both expose `to_dict()` and `from_dict()` and never store absolute paths in the task ledger. Add `Task.record_style()` and `Task.record_asset()` wrappers that append version `1` records.

- [ ] **Step 4: Run focused and existing tests**

  Run the two focused tests and then:

  ```sh
  .venv/bin/python -m pytest tests -q
  ```

  Expected: all existing tests remain green.

- [ ] **Step 5: Commit the contract boundary**

  ```sh
  git add src/openfigura/core/contracts.py src/openfigura/core/style.py src/openfigura/core/task.py src/openfigura/core/engine.py tests/test_contracts.py tests/test_style.py
  git commit -s -m "Add versioned asset and style contracts"
  ```

## Task 2: Add persistent stage graph and cache keys

**Files:**
- Create: `src/openfigura/core/workflow.py`
- Modify: `src/openfigura/core/task.py`
- Modify: `src/openfigura/core/engine.py`
- Modify: `src/openfigura/core/registry.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Write failing workflow tests**

  Test `Workflow.submit(step="inspect", inputs=[AssetRef(...)], params={...})` records `queued`; `Workflow.claim()` changes it to `running`; `Workflow.complete(output=...)` records `pass` and a deterministic cache key based on input hashes, backend id, backend version and canonical JSON parameters. Test that a changed parameter produces a different key, a failed step does not overwrite the previous successful output, and a cancelled task cannot be claimed.

- [ ] **Step 2: Run the focused tests**

  ```sh
  .venv/bin/python -m pytest tests/test_workflow.py -q
  ```

  Expected: FAIL with missing workflow implementation.

- [ ] **Step 3: Implement the stage state machine**

  Add states `queued`, `running`, `pass`, `fail`, `cancelled`, and `blocked`. Store each stage in `provenance.json` with input refs, output refs, device request, start/end time, error category and cache key. `claim()` must refuse non-queued stages; `complete()` must verify every output exists and hash it before recording success. Add `cancel()` and `resume()` without deleting evidence.

- [ ] **Step 4: Add cache lookup and backend declarations**

  Extend `Capabilities` with `device_types`, `memory_mb`, `network_required`, and `verified_cases`. Add a registry helper that returns a backend only when the requested capability and device policy match. Cache hits must create a new stage record pointing to the old verified output instead of copying unverified files.

- [ ] **Step 5: Run the full core suite**

  ```sh
  .venv/bin/python -m pytest tests -q
  ```

  Expected: all tests pass, with no ML import on a bare Python environment.

- [ ] **Step 6: Commit the workflow engine**

  ```sh
  git add src/openfigura/core/workflow.py src/openfigura/core/task.py src/openfigura/core/engine.py src/openfigura/core/registry.py tests/test_workflow.py
  git commit -s -m "Add persistent stage workflow and cache contracts"
  ```

## Task 3: Add CPU/GPU resource gate and external-node contract

**Files:**
- Create: `src/openfigura/core/resources.py`
- Modify: `src/openfigura/core/workflow.py`
- Modify: `src/openfigura/cli.py`
- Modify: `src/openfigura/mcp_server.py`
- Test: `tests/test_resources.py`

- [ ] **Step 1: Write failing resource tests**

  Test that a CPU stage can claim up to `cpu_workers`, a heavy GPU stage allows one claim per GPU by default, a second GPU claim is queued, a task declaring more memory than the device reports is blocked with a human-readable reason, and releasing a task makes the next queued task claimable.

- [ ] **Step 2: Run focused tests and observe failure**

  ```sh
  .venv/bin/python -m pytest tests/test_resources.py -q
  ```

- [ ] **Step 3: Implement resource leases**

  Implement `ResourcePool` with `register_device(id, kind, memory_mb, concurrency=1)`, `acquire(request)`, `release(lease_id)`, and `snapshot()`. Persist only lease and request evidence; do not persist live process handles. CPU stages use a bounded worker count; GPU stages use exclusive leases unless the backend explicitly declares safe concurrency.

- [ ] **Step 4: Expose status and cancellation through both frontends**

  Add CLI commands `openfigura task-status`, `task-cancel`, and `devices`. Add matching MCP tools returning the same schema. Test both frontends against a fake resource pool rather than starting a GPU process.

- [ ] **Step 5: Commit resource scheduling**

  ```sh
  git add src/openfigura/core/resources.py src/openfigura/core/workflow.py src/openfigura/cli.py src/openfigura/mcp_server.py tests/test_resources.py
  git commit -s -m "Add device-aware task resource scheduling"
  ```

## Task 4: Finish the verified 3D stage graph

**Files:**
- Modify: `src/openfigura/core/engine.py`
- Modify: `src/openfigura/backends/native_motion.py`
- Modify: `src/openfigura/backends/mia.py`
- Modify: `src/openfigura/cli.py`
- Modify: `src/openfigura/mcp_server.py`
- Test: `tests/test_engine.py`
- Test: `tests/test_autorig.py`
- Test: `tests/test_retarget.py`
- Documentation: `docs/neural-rigging.md`, `docs/PROGRESS.md`

- [ ] **Step 1: Add a fake end-to-end stage test**

  Build a fixture that runs `preflight → generate(fake) → inspect → autorig(fake) → retarget(fake) → export` and asserts every successful stage has an input/output hash, exactly one export candidate, and an export manifest. Add a failure branch where contact rejection quarantines the candidate and leaves the previous accepted asset unchanged.

- [ ] **Step 2: Run the new test before implementation**

  ```sh
  .venv/bin/python -m pytest tests/test_engine.py::test_end_to_end_stage_graph -q
  ```

- [ ] **Step 3: Adapt existing verbs to workflow records**

  Keep the current engine function signatures, but wrap each operation in a stage record. Successful `autorig` and `retarget` must use the existing structural and contact gates; failed tool-owned files must continue to move under `artifacts/rejected/<id>/`. Export must require a matching successful output hash.

- [ ] **Step 4: Run the real control-character proof**

  Re-run the existing Bunny CPU/Mac motion evidence using the external runtime, then re-import the final GLB and record the contact report. Keep the Xiaoman rejection as a negative case; do not promote it to a baseline.

- [ ] **Step 5: Commit the verified 3D graph**

  ```sh
  git add src/openfigura/core/engine.py src/openfigura/backends/native_motion.py src/openfigura/backends/mia.py src/openfigura/cli.py src/openfigura/mcp_server.py tests/test_engine.py tests/test_autorig.py tests/test_retarget.py docs/neural-rigging.md docs/PROGRESS.md
  git commit -s -m "Connect verified 3D stages through the workflow engine"
  ```

## Task 5: Implement the 2D pixel style pipeline

**Files:**
- Create: `src/openfigura/backends/pixel.py`
- Create: `src/openfigura/backends/pixel_worker.py`
- Create: `src/openfigura/core/pixel.py`
- Modify: `src/openfigura/core/engine.py`
- Modify: `src/openfigura/cli.py`
- Modify: `src/openfigura/mcp_server.py`
- Test: `tests/test_pixel.py`
- Test: `tests/test_pixel_worker.py`
- Documentation: `docs/pixel-pipeline.md`

- [ ] **Step 1: Write deterministic pixel tests**

  Use a generated 16×16 RGBA fixture and a style spec with a four-colour palette. Test integer scaling, nearest-neighbour reduction, palette mapping, transparent-background preservation, deterministic output bytes, anchor extraction, and sprite-sheet metadata for two frames. Test that a non-integer scale, empty palette, and mismatched frame dimensions fail before writing output.

- [ ] **Step 2: Run focused tests and observe failure**

  ```sh
  .venv/bin/python -m pytest tests/test_pixel.py tests/test_pixel_worker.py -q
  ```

- [ ] **Step 3: Implement the CPU pixel backend**

  Implement a Pillow-optional backend with a standard-library fallback for PNG metadata checks. The worker receives a JSON config containing input frames, `StyleSpec`, output directory and source kind (`render3d`, `direct2d`, or `manual_revision`). It must emit `frames/*.png`, `spritesheet.png`, `animation.json`, `style-report.json`, and a provenance fragment. Never overwrite source frames.

- [ ] **Step 4: Add 3D render-sequence adapter**

  Add an adapter that accepts fixed-camera render outputs from Blender, records camera/light/pose parameters, and rejects mixed canvas sizes or missing frame numbers. The initial implementation may consume an existing render sequence; it must not invent animation poses.

- [ ] **Step 5: Add CLI and MCP mirrors**

  Add `openfigura pixelize` and `figura_pixelize` with identical fields: input directory, style spec, source kind, output task, and optional palette. Return the same manifest and report structure.

- [ ] **Step 6: Validate one real character sequence**

  Run a fixed Bunny or Xiaoman render sequence through pixelization, inspect the sheet visually, and store the evidence outside git. Do not mark aesthetic approval automatically.

- [ ] **Step 7: Commit the pixel pipeline**

  ```sh
  git add src/openfigura/backends/pixel.py src/openfigura/backends/pixel_worker.py src/openfigura/core/pixel.py src/openfigura/core/engine.py src/openfigura/cli.py src/openfigura/mcp_server.py tests/test_pixel.py tests/test_pixel_worker.py docs/pixel-pipeline.md
  git commit -s -m "Add deterministic 2D pixel asset pipeline"
  ```

## Task 6: Define community backend and workflow manifests

**Files:**
- Create: `src/openfigura/core/manifest.py`
- Create: `schemas/backend-manifest-v1.json`
- Create: `schemas/workflow-manifest-v1.json`
- Modify: `src/openfigura/core/registry.py`
- Modify: `docs/2026-10-08-3dgenstudio-review.md`
- Test: `tests/test_manifest.py`
- Documentation: `docs/community-extensions.md`

- [ ] **Step 1: Write manifest validation tests**

  Test that a backend manifest requires `id`, `version`, `license`, `entrypoint`, `capabilities`, `hardware`, `network`, and `verified_cases`; rejects duplicate ids and unsupported schema versions; and records model-weight licenses separately from source-code licenses.

- [ ] **Step 2: Run focused tests**

  ```sh
  .venv/bin/python -m pytest tests/test_manifest.py -q
  ```

- [ ] **Step 3: Implement manifest loading in isolation**

  Add `load_backend_manifest(path)` and `load_workflow_manifest(path)` that validate JSON, resolve only declared relative entrypoints, and return a report with `experimental`, `community_verified`, or `official_verified`. Do not execute entrypoints during validation.

- [ ] **Step 4: Add an extension guide and example**

  Document a minimal pixel backend and a ComfyUI workflow manifest with explicit input/output contracts, hardware requirements, network behavior, evidence paths and license fields. State that 3DGenStudio code is not copied and that upstream licenses remain authoritative.

- [ ] **Step 5: Commit the ecosystem contract**

  ```sh
  git add src/openfigura/core/manifest.py schemas/backend-manifest-v1.json schemas/workflow-manifest-v1.json src/openfigura/core/registry.py tests/test_manifest.py docs/community-extensions.md docs/2026-10-08-3dgenstudio-review.md
  git commit -s -m "Define verified community extension manifests"
  ```

## Task 7: Add a read-only local workbench and external integration surface

**Files:**
- Create: `workbench/README.md`
- Create: `workbench/package.json`
- Create: `workbench/index.html`
- Create: `workbench/src/main.tsx`
- Create: `workbench/src/app.tsx`
- Create: `workbench/src/styles.css`
- Create: `src/openfigura/http_server.py`
- Modify: `src/openfigura/mcp_server.py`
- Test: `tests/test_http_server.py`
- Documentation: `docs/workbench.md`

- [ ] **Step 1: Define the HTTP read/submit contract tests**

  Test `GET /health`, `GET /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/stages/{stage}/retry`, and `POST /tasks/{id}/cancel`. The test server uses a temporary task root and never serves arbitrary filesystem paths.

- [ ] **Step 2: Implement the local HTTP adapter**

  Use the Python standard library HTTP server. Bind to loopback by default, require an explicit `--allow-network` for non-loopback binding, return JSON only, and delegate every operation to `core.workflow`. Do not add a second scheduler.

- [ ] **Step 3: Scaffold the workbench UI**

  Add a minimal Vite/React page with project selector, stage cards, asset preview links, style-spec editor and report panel. The page polls task status and submits only the documented HTTP operations; it does not run Blender, ComfyUI or Python workers in the browser.

- [ ] **Step 4: Add external Agent integration examples**

  Document MCP, CLI and HTTP examples for a complete task and a failed-stage retry. Add a smoke test that the three entrypoints expose matching field names for status, artifact references and errors.

- [ ] **Step 5: Commit the workbench surface**

  ```sh
  git add workbench src/openfigura/http_server.py src/openfigura/mcp_server.py tests/test_http_server.py docs/workbench.md
  git commit -s -m "Add local workbench and external task API"
  ```

## Task 8: End-to-end evidence, packaging and release gate

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify: `docs/PROGRESS.md`
- Modify: `docs/usage.md`
- Test: `tests/test_package.py`

- [ ] **Step 1: Add package resource tests**

  Assert the wheel contains worker scripts, manifest schemas, attribution files and no weights, GLBs, task outputs or runtime binaries.

- [ ] **Step 2: Run all tests and build the wheel**

  ```sh
  .venv/bin/python -m pytest tests -q
  .venv/bin/python -m pip wheel . --no-deps -w /tmp/openfigura-wheel
  ```

  Expected: all tests pass and the wheel resource test passes.

- [ ] **Step 3: Run the real evidence matrix**

  Verify one 3D control character, one negative rigging case, one 3D-to-2D sequence, one direct-2D input, and one resource-queue scenario. Store renders, manifests, logs and hashes under a dated Desktop evidence directory, not in git.

- [ ] **Step 4: Update public documentation**

  Describe the two hardware tiers, 3D／2D routes, CLI/MCP/HTTP entrypoints, community manifest rules, license boundaries and the difference between technical checks and human visual approval. Update roadmap checkboxes only for features backed by evidence.

- [ ] **Step 5: Perform final review and commit**

  Run `git diff --check`, inspect `git status --short`, confirm unrelated golden candidates remain unstaged, review the manifest and license files, then commit with DCO sign-off. Push only after the user explicitly requests the release push.

## Plan self-review

- The product spec's 3D route is covered by Tasks 1–4; the 2D route is covered by Task 5; ecosystem manifests by Task 6; IDE and external integrations by Task 7; evidence and documentation by Task 8.
- No task installs model weights or copies 3DGenStudio code. Every external backend remains optional and license-scoped.
- The contract names are consistent: `StyleSpec`, `AssetRef`, `Workflow`, `ResourcePool`, `load_backend_manifest`, and the stage states are defined before later tasks use them.
- The plan keeps the bare-core test requirement: worker and heavy-model tests use fakes; real hardware trials are separate evidence steps.
- Failed candidates remain recoverable under evidence directories but are never normal export inputs.
