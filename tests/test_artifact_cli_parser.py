import unittest

from openclaw_mem.cli import build_parser


class TestArtifactCliParser(unittest.TestCase):
    def test_artifact_parser_subcommands(self) -> None:
        a = build_parser().parse_args(["artifact", "stash"])
        self.assertEqual(a.cmd, "artifact")
        self.assertEqual(a.artifact_cmd, "stash")
        self.assertTrue(a.json)

        a_no_json = build_parser().parse_args(["artifact", "stash", "--no-json"])
        self.assertFalse(a_no_json.json)

        b = build_parser().parse_args(["artifact", "fetch", "ocm_artifact:v1:sha256:" + ("a" * 64)])
        self.assertEqual(b.cmd, "artifact")
        self.assertEqual(b.artifact_cmd, "fetch")
        self.assertTrue(b.json)

        c = build_parser().parse_args(["artifact", "fetch", "--no-json", "ocm_artifact:v1:sha256:" + ("a" * 64)])
        self.assertFalse(c.json)

        d = build_parser().parse_args(["artifact", "peek", "ocm_artifact:v1:sha256:" + ("a" * 64)])
        self.assertEqual(d.cmd, "artifact")
        self.assertEqual(d.artifact_cmd, "peek")
        self.assertTrue(d.json)

        d_no_json = build_parser().parse_args(["artifact", "peek", "--no-json", "ocm_artifact:v1:sha256:" + ("a" * 64)])
        self.assertFalse(d_no_json.json)

        e = build_parser().parse_args(
            [
                "artifact",
                "compact-receipt",
                "--command",
                "git status",
                "--tool",
                "rtk",
                "--compact-text",
                "ok main",
                "--raw-handle",
                "ocm_artifact:v1:sha256:" + ("a" * 64),
            ]
        )
        self.assertEqual(e.cmd, "artifact")
        self.assertEqual(e.artifact_cmd, "compact-receipt")
        self.assertTrue(e.json)

        e_no_json = build_parser().parse_args(
            [
                "artifact",
                "compact-receipt",
                "--command",
                "git status",
                "--compact-text",
                "ok main",
                "--raw-handle",
                "ocm_artifact:v1:sha256:" + ("a" * 64),
                "--no-json",
            ]
        )
        self.assertFalse(e_no_json.json)


if __name__ == "__main__":
    unittest.main()
