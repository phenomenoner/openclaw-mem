import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from openclaw_mem.cli import _connect, _insert_observation, cmd_writeback_lancedb


class TestWritebackLanceDbIntegration(unittest.TestCase):
    def setUp(self):
        self.engine_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "extensions",
            "openclaw-mem-engine",
        )

    def _require_node(self):
        if shutil.which("node") is None:
            self.skipTest("node is not available")

        if not os.path.isdir(os.path.join(self.engine_path, "node_modules")):
            self.skipTest("openclaw-mem-engine node_modules not present")

    def _node(self, args, *, cwd=None):
        self._require_node()
        proc = subprocess.run(
            ["node", *args],
            cwd=cwd or self.engine_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"node failed: {proc.stderr or proc.stdout}")
        return proc.stdout

    def test_writeback_updates_only_missing_fields_by_default(self):
        self._require_node()

        uuid_a = "11111111-1111-1111-1111-111111111111"
        uuid_b = "22222222-2222-2222-2222-222222222222"

        with tempfile.TemporaryDirectory() as td:
            sqlite_path = os.path.join(td, "mem.sqlite")
            lancedb_path = os.path.join(td, "lancedb")
            table = "memories"

            # 1) Create LanceDB table with two rows:
            # - A has meaningful existing values (should not be overwritten)
            # - B has missing/empty values (should be filled)
            rows_path = os.path.join(td, "rows.json")
            with open(rows_path, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "id": uuid_a,
                            "text": "row-a",
                            "createdAt": 1,
                            "category": "preference",
                            "importance": 0.42,
                            "importance_label": "nice_to_have",
                            "scope": "existing-scope",
                            "trust_tier": "trusted",
                        },
                        {
                            "id": uuid_b,
                            "text": "row-b",
                            "createdAt": 1,
                            "category": "",
                            "importance": None,
                            "importance_label": "",
                            "scope": "",
                            "trust_tier": "",
                        },
                    ],
                    f,
                    ensure_ascii=False,
                )

            create_script = os.path.join(self.engine_path, "_test_create_table.mjs")
            query_script = os.path.join(self.engine_path, "_test_dump_row.mjs")
            try:
                with open(create_script, "w", encoding="utf-8") as f:
                    f.write(
                        "import { readFile } from 'node:fs/promises';\n"
                        "import { connect } from '@lancedb/lancedb';\n"
                        "const [dbPath, tableName, rowsPath] = process.argv.slice(2);\n"
                        "const rows = JSON.parse(await readFile(rowsPath, 'utf8'));\n"
                        "const db = await connect(dbPath);\n"
                        "await db.createTable(tableName, rows, { mode: 'overwrite' });\n"
                        "console.log('ok');\n"
                        "await db.close?.();\n"
                    )

                with open(query_script, "w", encoding="utf-8") as f:
                    f.write(
                        "import { connect } from '@lancedb/lancedb';\n"
                        "const [dbPath, tableName, id] = process.argv.slice(2);\n"
                        "const db = await connect(dbPath);\n"
                        "const table = await db.openTable(tableName);\n"
                        "const rows = await table.query().limit(1024).toArray();\n"
                        "const found = rows.find((row) => String(row?.id ?? '') === String(id));\n"
                        "console.log(JSON.stringify(found ?? null));\n"
                        "await db.close?.();\n"
                    )

                self._node([create_script, lancedb_path, table, rows_path])

                # 2) Create SQLite ledger + observations.
                conn = _connect(sqlite_path)
                _insert_observation(
                    conn,
                    {
                        "kind": "preference",
                        "summary": "row-a obs",
                        "tool_name": "memory_store",
                        "detail": {
                            "memory_id": uuid_a,
                            "importance": {"score": 0.9, "label": "must_remember"},
                            "scope": "new-scope",
                            "trust_tier": "untrusted",
                            "category": "decision",
                        },
                    },
                )
                _insert_observation(
                    conn,
                    {
                        "kind": "decision",
                        "summary": "row-b obs",
                        "tool_name": "memory_store",
                        "detail": {
                            "memory_id": uuid_b,
                            "importance": {"score": 0.9, "label": "must_remember"},
                            "scope": "proj/test",
                            "trust_tier": "trusted",
                            "category": "decision",
                        },
                    },
                )

                # 3) Run writeback.
                args = type(
                    "Args",
                    (),
                    {
                        "json": True,
                        "dry_run": False,
                        "limit": 10,
                        "batch": 50,
                        "lancedb": lancedb_path,
                        "table": table,
                        "force": False,
                        "force_fields": "",
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_writeback_lancedb(conn, args)

                out = json.loads(buf.getvalue())
                self.assertTrue(out["ok"])
                self.assertEqual(out["updated"], 1)
                self.assertEqual(out["overwritten"], 0)
                self.assertEqual(out["overwrittenFields"], 0)
                self.assertEqual(out["missing"], 0)

                # 4) Verify LanceDB rows.
                row_a = json.loads(self._node([query_script, lancedb_path, table, uuid_a]))
                row_b = json.loads(self._node([query_script, lancedb_path, table, uuid_b]))

                # Row A unchanged.
                self.assertEqual(row_a["importance"], 0.42)
                self.assertEqual(row_a["importance_label"], "nice_to_have")
                self.assertEqual(row_a["scope"], "existing-scope")
                self.assertEqual(row_a["trust_tier"], "trusted")
                self.assertEqual(row_a["category"], "preference")

                # Row B filled.
                self.assertEqual(row_b["importance"], 0.9)
                self.assertEqual(row_b["importance_label"], "must_remember")
                self.assertEqual(row_b["scope"], "proj/test")
                self.assertEqual(row_b["trust_tier"], "trusted")
                self.assertEqual(row_b["category"], "decision")

            finally:
                for p in (create_script, query_script):
                    try:
                        os.remove(p)
                    except FileNotFoundError:
                        pass
