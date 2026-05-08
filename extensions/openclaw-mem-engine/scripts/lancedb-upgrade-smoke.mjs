#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const args = new Map();
for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg.startsWith('--')) {
    const key = arg.slice(2);
    const next = process.argv[i + 1];
    if (next && !next.startsWith('--')) {
      args.set(key, next);
      i += 1;
    } else {
      args.set(key, 'true');
    }
  }
}

const currentVersion = args.get('current') ?? '0.26.2';
const candidateVersion = args.get('candidate') ?? '0.27.2';
const vectorDim = Number(args.get('vector-dim') ?? '1536');
const liveDbPath = expandHome(args.get('live-db') ?? '~/.openclaw/memory/lancedb');
const runId = args.get('run-id') ?? new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
const runRoot = path.resolve(args.get('out') ?? path.join(repoRoot, '.state/openclaw-mem/lancedb-upgrade-smoke', runId));
const skipLiveCopy = args.get('skip-live-copy') === 'true';

function expandHome(p) {
  if (!p) return p;
  if (p === '~') return os.homedir();
  if (p.startsWith('~/')) return path.join(os.homedir(), p.slice(2));
  return p;
}

function run(cmd, cmdArgs, options = {}) {
  const result = spawnSync(cmd, cmdArgs, {
    stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    encoding: 'utf8',
    ...options,
  });
  if (result.status !== 0) {
    const detail = [
      `command failed: ${cmd} ${cmdArgs.join(' ')}`,
      `exit: ${result.status}`,
      result.stdout ? `stdout:\n${result.stdout}` : '',
      result.stderr ? `stderr:\n${result.stderr}` : '',
    ].filter(Boolean).join('\n');
    throw new Error(detail);
  }
  return result;
}

const workerSource = String.raw`
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import * as lancedb from '@lancedb/lancedb';

const mode = process.argv[2];
const receiptPath = process.argv[3];
const dbPath = process.argv[4];
const vectorDim = Number(process.env.VECTOR_DIM ?? '1536');
const version = process.env.LANCEDB_VERSION ?? 'unknown';
const makeVector = (seed = 0) => Array.from({ length: vectorDim }, (_, i) => ((i + seed) % 17) / 17);
const receipt = {
  ok: false,
  mode,
  version,
  dbPath,
  vectorDim,
  node: process.version,
  platform: process.platform,
  arch: process.arch,
  checks: [],
  startedAt: new Date().toISOString(),
};
async function check(name, fn) {
  const started = Date.now();
  try {
    const detail = await fn();
    receipt.checks.push({ name, ok: true, ms: Date.now() - started, detail });
    return detail;
  } catch (err) {
    receipt.checks.push({ name, ok: false, ms: Date.now() - started, error: String(err?.stack || err?.message || err) });
    throw err;
  }
}
const schemaRow = {
  id: '__schema__',
  text: '',
  vector: makeVector(0).map(() => 0),
  createdAt: 0,
  category: 'other',
  importance: 0,
  importance_label: 'unknown',
  scope: 'global',
  trust_tier: 'unknown',
};
const rows = [
  { id: 'm1', text: 'alpha fox memory global', vector: makeVector(1), createdAt: 100, category: 'decision', importance: 0.9, importance_label: 'must_remember', scope: 'global', trust_tier: 'trusted' },
  { id: 'm2', text: 'beta cat memory scoped', vector: makeVector(2), createdAt: 200, category: 'todo', importance: 0.5, importance_label: 'nice_to_have', scope: 'proj', trust_tier: 'trusted' },
];
async function runFresh() {
  await fs.rm(dbPath, { recursive: true, force: true });
  await fs.mkdir(path.dirname(dbPath), { recursive: true });
  const db = await check('connect', () => lancedb.connect(dbPath));
  await check('tableNames.initial', async () => await db.tableNames());
  const table = await check('createTable.implicitSchema', async () => await db.createTable('memories', [schemaRow]));
  await check('delete.schema', async () => await table.delete('id = "__schema__"'));
  await check('add.rows', async () => await table.add(rows));
  await exerciseTable(table);
  await check('reopen.existing.table', async () => {
    const db2 = await lancedb.connect(dbPath);
    const names = await db2.tableNames();
    if (!names.includes('memories')) throw new Error('missing memories table after reopen');
    const t2 = await db2.openTable('memories');
    const found = await t2.query().select(['id']).limit(10).toArray();
    if (found.length !== 2) throw new Error('unexpected reopen row count ' + found.length);
    return { names, rowCount: found.length };
  });
}
async function runCreateOnly() {
  await fs.rm(dbPath, { recursive: true, force: true });
  await fs.mkdir(path.dirname(dbPath), { recursive: true });
  const db = await check('connect', () => lancedb.connect(dbPath));
  const table = await check('createTable.implicitSchema', async () => await db.createTable('memories', [schemaRow]));
  await check('delete.schema', async () => await table.delete('id = "__schema__"'));
  await check('add.rows', async () => await table.add(rows));
  await exerciseTable(table);
}
async function runReadWriteExisting() {
  const db = await check('connect.existing', () => lancedb.connect(dbPath));
  const names = await check('tableNames.existing', async () => await db.tableNames());
  if (!names.includes('memories')) throw new Error('missing memories table in existing DB');
  const table = await check('openTable.existing', async () => await db.openTable('memories'));
  await exerciseTable(table);
  await check('add.delete.candidateRow', async () => {
    const id = 'candidate-' + Date.now();
    await table.add([{ ...rows[0], id, text: 'candidate transient row' }]);
    const before = await table.query().select(['id']).where("id = '" + id + "'").limit(1).toArray();
    if (before.length !== 1) throw new Error('candidate row was not added');
    const deleted = await table.delete("id = '" + id + "'");
    const after = await table.query().select(['id']).where("id = '" + id + "'").limit(1).toArray();
    if (after.length !== 0) throw new Error('candidate row was not deleted');
    return { deleteReturn: deleted ?? null };
  });
}
async function runReadOnlySnapshot() {
  const db = await check('connect.snapshot', () => lancedb.connect(dbPath));
  const names = await check('tableNames.snapshot', async () => await db.tableNames());
  const tables = [];
  for (const name of names) {
    const table = await db.openTable(name);
    const sample = await table.query().limit(3).toArray();
    tables.push({ name, sampleCount: sample.length, columns: sample[0] ? Object.keys(sample[0]).sort() : [] });
  }
  return tables;
}
async function exerciseTable(table) {
  await check('query.select.where.limit', async () => {
    const found = await table.query().select(['id', 'text', 'createdAt', 'scope']).where("scope = 'global'").limit(5).toArray();
    if (found.length < 1 || !found.some((row) => row.id === 'm1')) throw new Error('unexpected query rows ' + JSON.stringify(found));
    return found;
  });
  await check('query.orderBy.available', async () => {
    const q = table.query().select(['id', 'createdAt']).where("scope IN ('global', 'proj')");
    const available = typeof q.orderBy === 'function';
    const found = available ? await q.orderBy('createdAt DESC').limit(2).toArray() : await q.limit(2).toArray();
    return { available, ids: found.map((row) => row.id) };
  });
  await check('vectorSearch.where.limit', async () => {
    if (typeof table.vectorSearch !== 'function') throw new Error('vectorSearch is not a function');
    const found = await table.vectorSearch(makeVector(1)).where("scope = 'global'").limit(1).toArray();
    if (found.length !== 1 || found[0].id !== 'm1' || typeof found[0]._distance !== 'number') throw new Error('unexpected vector rows ' + JSON.stringify(found));
    return { id: found[0].id, distance: found[0]._distance };
  });
  await check('fts.search.where.limit', async () => {
    const found = await table.search('fox', 'fts', ['text']).where("scope = 'global'").limit(3).toArray();
    if (found.length < 1 || !found.some((row) => row.id === 'm1')) throw new Error('unexpected fts rows ' + JSON.stringify(found));
    return found.map((row) => ({ id: row.id, score: typeof row._score === 'number' ? row._score : null }));
  });
}
try {
  if (mode === 'fresh') await runFresh();
  else if (mode === 'create-only') await runCreateOnly();
  else if (mode === 'readwrite-existing') await runReadWriteExisting();
  else if (mode === 'readonly-snapshot') await runReadOnlySnapshot();
  else throw new Error('unknown mode ' + mode);
  receipt.ok = true;
} catch (err) {
  receipt.ok = false;
  receipt.error = String(err?.stack || err?.message || err);
  process.exitCode = 1;
} finally {
  receipt.finishedAt = new Date().toISOString();
  await fs.mkdir(path.dirname(receiptPath), { recursive: true });
  await fs.writeFile(receiptPath, JSON.stringify(receipt, null, 2));
  console.log(JSON.stringify({ ok: receipt.ok, mode, version, receiptPath }));
}
`;

await fs.mkdir(runRoot, { recursive: true });
await fs.writeFile(path.join(runRoot, 'smoke-worker.mjs'), workerSource);

async function setupPackage(version) {
  const dir = path.join(runRoot, `pkg-${version}`);
  await fs.mkdir(dir, { recursive: true });
  run('npm', ['init', '-y'], { cwd: dir, capture: true });
  run('npm', ['install', '--ignore-scripts', '--no-audit', '--no-fund', `@lancedb/lancedb@${version}`], { cwd: dir, capture: true });
  await fs.copyFile(path.join(runRoot, 'smoke-worker.mjs'), path.join(dir, 'smoke-worker.mjs'));
  return dir;
}

async function runWorker(pkgDir, version, mode, dbPath, receiptName) {
  const receiptPath = path.join(runRoot, receiptName);
  run('node', ['smoke-worker.mjs', mode, receiptPath, dbPath], {
    cwd: pkgDir,
    env: { ...process.env, LANCEDB_VERSION: version, VECTOR_DIM: String(vectorDim) },
  });
  return JSON.parse(await fs.readFile(receiptPath, 'utf8'));
}

async function copyDir(src, dest) {
  await fs.rm(dest, { recursive: true, force: true });
  await fs.mkdir(path.dirname(dest), { recursive: true });
  // Prefer the platform copy tool: LanceDB directories can be multi-GB, and
  // fs.cp is noticeably slower on large local stores. --reflink=auto keeps the
  // gate isolated while allowing cheap copy-on-write snapshots when supported.
  run('cp', ['-a', '--reflink=auto', src, dest], { capture: true });
}

const summary = {
  ok: false,
  runId,
  runRoot,
  currentVersion,
  candidateVersion,
  vectorDim,
  liveDbPath,
  skipLiveCopy,
  checks: [],
  startedAt: new Date().toISOString(),
};
try {
  const currentPkg = await setupPackage(currentVersion);
  const candidatePkg = await setupPackage(candidateVersion);
  summary.checks.push(await runWorker(currentPkg, currentVersion, 'fresh', path.join(runRoot, `fresh-${currentVersion}`), `fresh-${currentVersion}.json`));
  summary.checks.push(await runWorker(candidatePkg, candidateVersion, 'fresh', path.join(runRoot, `fresh-${candidateVersion}`), `fresh-${candidateVersion}.json`));
  const crossDb = path.join(runRoot, 'cross-db');
  summary.checks.push(await runWorker(currentPkg, currentVersion, 'create-only', crossDb, `cross-create-${currentVersion}.json`));
  summary.checks.push(await runWorker(candidatePkg, candidateVersion, 'readwrite-existing', crossDb, `cross-readwrite-${candidateVersion}.json`));
  if (!skipLiveCopy) {
    try {
      const st = await fs.stat(liveDbPath);
      if (st.isDirectory()) {
        const snapshot = path.join(runRoot, 'live-db-snapshot');
        await copyDir(liveDbPath, snapshot);
        summary.checks.push(await runWorker(candidatePkg, candidateVersion, 'readonly-snapshot', snapshot, `live-copy-readonly-${candidateVersion}.json`));
      } else {
        summary.checks.push({ ok: true, mode: 'live-copy-skipped', reason: 'live DB path exists but is not a directory', liveDbPath });
      }
    } catch (err) {
      if (err?.code === 'ENOENT') summary.checks.push({ ok: true, mode: 'live-copy-skipped', reason: 'live DB path missing', liveDbPath });
      else throw err;
    }
  }
  summary.ok = summary.checks.every((item) => item.ok === true);
} catch (err) {
  summary.ok = false;
  summary.error = String(err?.stack || err?.message || err);
  process.exitCode = 1;
} finally {
  summary.finishedAt = new Date().toISOString();
  await fs.writeFile(path.join(runRoot, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify({ ok: summary.ok, runRoot, summary: path.join(runRoot, 'summary.json') }, null, 2));
}
