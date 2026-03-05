import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import {
  collectDocsFiles,
  docsIngestWithCli,
  docsSearchWithCli,
  __private__,
} from './docsColdLane.js';

test('collectDocsFiles respects roots and globs', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'docs-cold-lane-'));
  const docsDir = path.join(dir, 'docs');
  await fs.mkdir(path.join(docsDir, 'DECISIONS'), { recursive: true });
  await fs.mkdir(path.join(docsDir, 'notes'), { recursive: true });

  await fs.writeFile(path.join(docsDir, 'DECISIONS', 'a.md'), '# A\n', 'utf8');
  await fs.writeFile(path.join(docsDir, 'notes', 'b.md'), '# B\n', 'utf8');
  await fs.writeFile(path.join(docsDir, 'notes', 'b.txt'), 'noop', 'utf8');

  const out = await collectDocsFiles({
    sourceRoots: [docsDir],
    sourceGlobs: ['DECISIONS/*.md'],
  });

  assert.equal(out.files.length, 1);
  assert.ok(out.files[0].endsWith(path.join('DECISIONS', 'a.md')));
  assert.equal(out.missingRoots.length, 0);
});

test('collectDocsFiles default **/*.md matches root markdown files', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'docs-cold-lane-'));
  const docsDir = path.join(dir, 'docs');
  await fs.mkdir(path.join(docsDir, 'DECISIONS'), { recursive: true });

  await fs.writeFile(path.join(docsDir, 'README.md'), '# Root\n', 'utf8');
  await fs.writeFile(path.join(docsDir, 'DECISIONS', 'a.md'), '# A\n', 'utf8');

  const out = await collectDocsFiles({
    sourceRoots: [docsDir],
    sourceGlobs: ['**/*.md'],
  });

  const basenames = out.files.map((fp) => path.basename(fp)).sort();
  assert.ok(basenames.includes('README.md'));
  assert.ok(basenames.includes('a.md'));
});

test('docsIngestWithCli fail-open on empty source roots', async () => {
  const result = await docsIngestWithCli({
    sqlitePath: '/tmp/non-existent.sqlite',
    sourceRoots: [],
    sourceGlobs: ['**/*.md'],
    maxChunkChars: 1400,
    embedOnIngest: false,
  });

  assert.equal(result.receipt.ok, false);
  assert.equal(result.receipt.skipped, true);
  assert.equal(result.receipt.skipReason, 'no_source_roots');
});

test('docsSearchWithCli validates empty query', async () => {
  const out = await docsSearchWithCli({
    sqlitePath: '/tmp/non-existent.sqlite',
    query: '   ',
    scope: 'global',
    limit: 3,
    maxSnippetChars: 200,
    searchFtsK: 20,
    searchVecK: 20,
    searchRrfK: 60,
    scopeMappingStrategy: 'repo_prefix',
    scopeMap: {},
  });

  assert.equal(out.items.length, 0);
  assert.equal(out.error, 'empty_query');
});

test('matchesScope map strategy fails closed when scope is unmapped', () => {
  const row = { repo: 'local', path: 'DECISIONS/a.md' };
  const ok = __private__.matchesScope(row, 'openclaw-mem', 'map', {});
  assert.equal(ok, false);
});
