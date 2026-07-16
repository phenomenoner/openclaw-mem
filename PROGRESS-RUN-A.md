| task | status | commit | note |
| --- | --- | --- | --- |
| T00 | done | HEAD-on-commit | Branch `feat/v2-run-a`; baseline 789 passed, 3 skipped, 4 cp950 decode warnings, 87 subtests passed in 256.91s. |
| T01 | done | HEAD-on-commit | Locked 253 current command paths and help-smoked all 52 top-level commands; 54 tests passed in 5.55s. |
| T02 | done | HEAD-on-commit | Added explicit UTF-8 replacement decoding to 67 subprocess text calls across product/tools/tests; AST guard 1 passed; focused slice 58 passed, 1 skipped. |
| T03 | done | HEAD-on-commit | Added additive meta/user_version=1 stamp and `db info`; 58 DB/surface tests plus 149 CLI tests and 26 subtests passed. |
| T04 | done | HEAD-on-commit | Added migration registry, stamped connect fast-path, and future-version rejection; full suite 852 passed, 3 skipped, 87 subtests in 367.37s with prior cp950 warnings eliminated. |
