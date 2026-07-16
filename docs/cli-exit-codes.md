# CLI exit codes and error receipts

Every structured error receipt includes both `error` and `hint`. The hint names
a recovery action, command, or documentation path. Nested error receipts follow
the same contract.

| Code | Meaning | Caller action |
| --- | --- | --- |
| `0` | The command completed successfully. | Consume the receipt or output. |
| `1` | An operation failed at runtime or could not complete safely. | Follow `hint`, correct the runtime condition, and retry. |
| `2` | The command input, configuration, or requested operation is invalid. | Correct the invocation/configuration described by `hint`. |
| `3` | Optional compatibility-mode failure. Reserved for callers that explicitly request a strict compatibility gate. | Upgrade or select the supported compatibility surface named by `hint`. |

Deprecation warnings remain additive and do not change a successful command's
exit code. A command that reports `ok: false` must not be treated as successful
merely because a nested compatibility adapter was available.

For command syntax, run `openclaw-mem --help-all`. For bootstrap/configuration
problems, run `openclaw-mem init --json` after correcting the reported TOML or
filesystem issue.
