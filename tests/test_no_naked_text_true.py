from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (REPO_ROOT / "openclaw_mem", REPO_ROOT / "tools")


def _is_subprocess_text_call(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in {"run", "Popen"}
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def test_subprocess_text_calls_declare_utf8_error_handling() -> None:
    violations: list[str] = []
    for root in SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _is_subprocess_text_call(node):
                    continue
                keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                text_value = keywords.get("text")
                if not isinstance(text_value, ast.Constant) or text_value.value is not True:
                    continue
                encoding = keywords.get("encoding")
                errors = keywords.get("errors")
                if not (
                    isinstance(encoding, ast.Constant)
                    and encoding.value == "utf-8"
                    and isinstance(errors, ast.Constant)
                    and errors.value == "replace"
                ):
                    relative = path.relative_to(REPO_ROOT)
                    violations.append(f"{relative}:{node.lineno}")
    assert not violations, (
        "subprocess text=True calls must set encoding='utf-8', errors='replace': "
        + ", ".join(violations)
    )
