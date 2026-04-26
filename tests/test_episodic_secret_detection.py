from openclaw_mem.cli import _episodic_guard_text_fragments, _looks_like_secret


def test_secret_detector_catches_new_high_risk_patterns():
    project_key = "sk-proj-" + ("A" * 24)
    github_pat = "github_pat_" + ("B" * 24)
    aws_secret = "aws_secret_access_key=" + ("C" * 40)
    bearer = "Authorization: Bearer " + ("D" * 32)

    assert _looks_like_secret(project_key)
    assert _looks_like_secret(github_pat)
    assert _looks_like_secret(aws_secret)
    assert _looks_like_secret(bearer)


def test_secret_detector_avoids_benign_auth_docs_text():
    assert not _looks_like_secret("Use bearer tokens for OAuth flows; keep token storage in vault.")
    assert not _looks_like_secret("Set aws_secret_access_key from environment variables.")


def test_guard_error_message_does_not_echo_secret_value():
    bearer_value = "Z" * 32
    payload = '{"auth":"Authorization: Bearer ' + bearer_value + '"}'

    try:
        _episodic_guard_text_fragments("safe summary", payload, None, allow_tool_output=False)
    except ValueError as exc:
        msg = str(exc)
        assert "secret-like content" in msg
        assert bearer_value not in msg
    else:
        raise AssertionError("expected ValueError for secret-like payload")
