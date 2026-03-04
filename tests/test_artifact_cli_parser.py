from openclaw_mem.cli import build_parser


def test_artifact_parser_subcommands() -> None:
    a = build_parser().parse_args(["artifact", "stash"])
    assert a.cmd == "artifact"
    assert a.artifact_cmd == "stash"

    b = build_parser().parse_args(["artifact", "fetch", "ocm_artifact:v1:sha256:" + ("a" * 64)])
    assert b.cmd == "artifact"
    assert b.artifact_cmd == "fetch"
    assert b.json is True

    c = build_parser().parse_args(["artifact", "fetch", "--no-json", "ocm_artifact:v1:sha256:" + ("a" * 64)])
    assert c.json is False

    d = build_parser().parse_args(["artifact", "peek", "ocm_artifact:v1:sha256:" + ("a" * 64)])
    assert d.cmd == "artifact"
    assert d.artifact_cmd == "peek"
