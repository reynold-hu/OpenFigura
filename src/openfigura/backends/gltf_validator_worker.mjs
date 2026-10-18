#!/usr/bin/env node
// Khronos glTF-Validator worker. Runs under a caller-provided Node + module.
// Config JSON path is the last argument: {model, module, report, max_issues}.
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const cfg = JSON.parse(await readFile(process.argv.at(-1), 'utf8'));
const require = createRequire(pathToFileURL(cfg.module + '/package.json'));
const validator = require(cfg.module);
const bytes = await readFile(cfg.model);
const result = await validator.validateBytes(new Uint8Array(bytes), {
  uri: 'model.glb',
  maxIssues: cfg.max_issues ?? 1000,
});
let version = null;
try {
  version = require(cfg.module + '/package.json').version ?? null;
} catch {}
const report = {
  validator: 'gltf-validator',
  validator_version: version,
  issues: result.issues ?? {},
};
await writeFile(cfg.report, JSON.stringify(report, null, 2) + '\n', 'utf8');
console.log('GLTF_VALIDATOR_DONE');
