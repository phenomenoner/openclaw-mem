from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


CONSULT_SCHEMA = "openclaw-mem.gbrain.consult.v0"
JOBS_SCHEMA_PREFIX = "openclaw-mem.gbrain.jobs"
DEFAULT_GBRAIN_BIN = "gbrain"
DEFAULT_CONSULT_TIMEOUT_MS = 1500
DEFAULT_JOBS_TIMEOUT_MS = 5000
DEFAULT_CONSULT_LIMIT = 4
PHASE2_ALLOWED_JOB_NAME = "embed"
REFRESH_RECOMMEND_SCHEMA = "openclaw-mem.graph.synth.recommend.v0"
MAX_GBRAIN_STDOUT_CHARS = 1_000_000
MAX_GBRAIN_RECEIPT_CHARS = 4000


@dataclass(frozen=True)
class GBrainCallResult:
    ok: bool
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    error: Optional[str] = None
    payload: Optional[Any] = None


def _truncate(text: str, limit: int = 240) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def _stringify_subprocess_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _run_gbrain_call(
    tool_name: str,
    payload: Dict[str, Any],
    *,
    gbrain_bin: str = DEFAULT_GBRAIN_BIN,
    timeout_ms: int = DEFAULT_JOBS_TIMEOUT_MS,
) -> GBrainCallResult:
    command = [gbrain_bin, "call", tool_name, json.dumps(payload, ensure_ascii=False)]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(0.1, timeout_ms / 1000.0),
            check=False,
        )
    except FileNotFoundError:
        return GBrainCallResult(
            ok=False,
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=f"gbrain binary not found: {gbrain_bin}",
        )
    except subprocess.TimeoutExpired as e:
        stdout = _truncate(_stringify_subprocess_text(e.stdout), MAX_GBRAIN_RECEIPT_CHARS)
        stderr = _truncate(_stringify_subprocess_text(e.stderr), MAX_GBRAIN_RECEIPT_CHARS)
        return GBrainCallResult(
            ok=False,
            command=command,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=f"gbrain call timed out after {timeout_ms}ms",
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    raw_stdout = _stringify_subprocess_text(completed.stdout)
    raw_stderr = _stringify_subprocess_text(completed.stderr)
    stdout = _truncate(raw_stdout, MAX_GBRAIN_RECEIPT_CHARS)
    stderr = _truncate(raw_stderr, MAX_GBRAIN_RECEIPT_CHARS)

    if completed.returncode != 0:
        return GBrainCallResult(
            ok=False,
            command=command,
            returncode=int(completed.returncode),
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            error=_truncate(stderr or stdout or f"gbrain call {tool_name} failed"),
        )

    if len(raw_stdout) > MAX_GBRAIN_STDOUT_CHARS:
        return GBrainCallResult(
            ok=False,
            command=command,
            returncode=int(completed.returncode),
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            error=f"gbrain JSON output too large: {len(raw_stdout)} chars",
        )

    try:
        parsed = json.loads(raw_stdout or "null")
    except Exception as e:
        return GBrainCallResult(
            ok=False,
            command=command,
            returncode=int(completed.returncode),
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            error=f"invalid gbrain JSON output: {e}",
        )

    return GBrainCallResult(
        ok=True,
        command=command,
        returncode=int(completed.returncode),
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        payload=parsed,
    )


def gbrain_binary_ready(gbrain_bin: str = DEFAULT_GBRAIN_BIN) -> bool:
    return bool(shutil.which(gbrain_bin))


def consult(
    query: str,
    *,
    limit: int = DEFAULT_CONSULT_LIMIT,
    timeout_ms: int = DEFAULT_CONSULT_TIMEOUT_MS,
    gbrain_bin: str = DEFAULT_GBRAIN_BIN,
    expand: bool = False,
) -> Dict[str, Any]:
    result = _run_gbrain_call(
        "query",
        {
            "query": str(query or "").strip(),
            "limit": max(1, int(limit)),
            "expand": bool(expand),
        },
        gbrain_bin=gbrain_bin,
        timeout_ms=timeout_ms,
    )

    out: Dict[str, Any] = {
        "schema": CONSULT_SCHEMA,
        "source": "gbrain",
        "query": {"text": str(query or "").strip()},
        "config": {
            "gbrain_bin": gbrain_bin,
            "limit": max(1, int(limit)),
            "timeout_ms": max(1, int(timeout_ms)),
            "expand": bool(expand),
        },
        "ok": bool(result.ok),
        "fail_open": not bool(result.ok),
        "timing": {"duration_ms": int(result.duration_ms)},
        "command": result.command,
        "items": [],
        "result_count": 0,
        "error": result.error,
    }

    if not result.ok:
        return out

    payload = result.payload
    rows = payload if isinstance(payload, list) else []
    items: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows[: max(1, int(limit))], start=1):
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or row.get("id") or f"hit-{idx}")
        score = row.get("score")
        try:
            score_value = round(float(score), 4)
        except Exception:
            score_value = None
        text = _truncate(str(row.get("chunk_text") or row.get("compiled_truth") or row.get("title") or ""), 280)
        record_ref = f"gbrain:{slug}"
        items.append(
            {
                "rank": idx,
                "recordRef": record_ref,
                "slug": slug,
                "title": row.get("title"),
                "score": score_value,
                "text": text,
                "stale": bool(row.get("stale", False)),
                "citations": {"recordRef": record_ref, "slug": slug},
            }
        )

    out["items"] = items
    out["result_count"] = len(items)
    out["bundle_text"] = "\n".join(f"- [{item['recordRef']}] {item['text']}" for item in items)
    return out


def trace_extension(consult_payload: Dict[str, Any]) -> Dict[str, Any]:
    items = list((consult_payload or {}).get("items") or [])
    return {
        "enabled": True,
        "ok": bool((consult_payload or {}).get("ok")),
        "fail_open": bool((consult_payload or {}).get("fail_open")),
        "error": (consult_payload or {}).get("error"),
        "result_count": int((consult_payload or {}).get("result_count") or 0),
        "timing": dict((consult_payload or {}).get("timing") or {}),
        "command": list((consult_payload or {}).get("command") or []),
        "record_refs": [str(item.get("recordRef") or "") for item in items if str(item.get("recordRef") or "")],
        "slugs": [str(item.get("slug") or "") for item in items if str(item.get("slug") or "")],
        "source": "gbrain",
    }


def build_refresh_recommendation(
    *,
    record_ref: str,
    consult_payload: Optional[Dict[str, Any]] = None,
    candidate_id: Optional[str] = None,
    max_evidence_refs: int = 4,
) -> Dict[str, Any]:
    target_ref = str(record_ref or "").strip()
    if not target_ref:
        raise ValueError("record_ref is required")

    consult_items = list((consult_payload or {}).get("items") or [])
    gbrain_refs = [
        str(item.get("recordRef") or "").strip()
        for item in consult_items
        if isinstance(item, dict) and str(item.get("recordRef") or "").strip()
    ]
    evidence_refs = [target_ref] + gbrain_refs[: max(0, int(max_evidence_refs))]
    query_text = str(((consult_payload or {}).get("query") or {}).get("text") or "").strip()
    consult_ok = bool((consult_payload or {}).get("ok"))

    reasons = ["gbrain_sidecar_signal"]
    if query_text:
        reasons.append(f"consult_query:{query_text}")
    if not consult_ok and consult_payload is not None:
        reasons.append("consult_fail_open")

    args = ["graph", "synth", "refresh", target_ref]
    item = {
        "candidate_id": str(candidate_id or f"gbrain-refresh:{target_ref}"),
        "action": "refresh_card",
        "reasons": reasons,
        "target": {
            "recordRef": target_ref,
        },
        "suggestion": {
            "args": args,
            "command": "openclaw-mem " + " ".join(args),
        },
        "evidence_refs": evidence_refs,
        "evidence": {
            "source": "gbrain_sidecar",
            "consult_ok": consult_ok,
            "consult_result_count": int((consult_payload or {}).get("result_count") or 0),
            "consult_query": query_text or None,
        },
        "auto_apply_eligible": False,
        "safe_for_auto_apply": False,
        "risk_level": "low",
        "risk_reasons": [],
    }
    return {
        "kind": REFRESH_RECOMMEND_SCHEMA,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": {
            "refreshSynthesis": 1,
            "compileSynthesis": 0,
            "noAction": 0,
            "items": 1,
            "synthesisCards": 1,
            "candidateCardSuggestions": 0,
        },
        "items": [item],
        "source": "gbrain_sidecar",
        "consult": {
            "ok": consult_ok,
            "query": query_text or None,
            "result_count": int((consult_payload or {}).get("result_count") or 0),
            "record_refs": gbrain_refs[: max(0, int(max_evidence_refs))],
        },
    }


def submit_job(
    *,
    name: str,
    data: Optional[Dict[str, Any]] = None,
    queue: str = "default",
    priority: int = 0,
    max_attempts: int = 3,
    delay: Optional[int] = None,
    gbrain_bin: str = DEFAULT_GBRAIN_BIN,
    timeout_ms: int = DEFAULT_JOBS_TIMEOUT_MS,
) -> Dict[str, Any]:
    if str(name or "").strip() != PHASE2_ALLOWED_JOB_NAME:
        raise ValueError(f"phase-2 job lane is bounded to '{PHASE2_ALLOWED_JOB_NAME}'")

    return _jobs_result(
        action="submit",
        call_result=_run_gbrain_call(
            "submit_job",
            {
                "name": PHASE2_ALLOWED_JOB_NAME,
                "data": dict(data or {}),
                "queue": str(queue or "default"),
                "priority": int(priority),
                "max_attempts": int(max_attempts),
                **({"delay": int(delay)} if delay is not None else {}),
            },
            gbrain_bin=gbrain_bin,
            timeout_ms=timeout_ms,
        ),
        timeout_ms=timeout_ms,
        gbrain_bin=gbrain_bin,
    )


def list_jobs(
    *,
    status: Optional[str] = None,
    queue: Optional[str] = None,
    limit: int = 20,
    name: str = PHASE2_ALLOWED_JOB_NAME,
    gbrain_bin: str = DEFAULT_GBRAIN_BIN,
    timeout_ms: int = DEFAULT_JOBS_TIMEOUT_MS,
) -> Dict[str, Any]:
    if str(name or PHASE2_ALLOWED_JOB_NAME).strip() != PHASE2_ALLOWED_JOB_NAME:
        raise ValueError(f"phase-2 job lane is bounded to '{PHASE2_ALLOWED_JOB_NAME}'")

    return _jobs_result(
        action="list",
        call_result=_run_gbrain_call(
            "list_jobs",
            {
                **({"status": str(status)} if status else {}),
                **({"queue": str(queue)} if queue else {}),
                "name": str(name or PHASE2_ALLOWED_JOB_NAME),
                "limit": max(1, int(limit)),
            },
            gbrain_bin=gbrain_bin,
            timeout_ms=timeout_ms,
        ),
        timeout_ms=timeout_ms,
        gbrain_bin=gbrain_bin,
    )


def retry_job(
    job_id: int,
    *,
    gbrain_bin: str = DEFAULT_GBRAIN_BIN,
    timeout_ms: int = DEFAULT_JOBS_TIMEOUT_MS,
) -> Dict[str, Any]:
    check = _run_gbrain_call(
        "get_job",
        {"id": int(job_id)},
        gbrain_bin=gbrain_bin,
        timeout_ms=timeout_ms,
    )
    if not check.ok:
        raise ValueError(check.error or f"unable to verify job {job_id} before retry")
    payload = check.payload if isinstance(check.payload, dict) else {}
    if str(payload.get("name") or "").strip() != PHASE2_ALLOWED_JOB_NAME:
        raise ValueError(f"job {job_id} is not in the '{PHASE2_ALLOWED_JOB_NAME}' family")

    return _jobs_result(
        action="retry",
        call_result=_run_gbrain_call(
            "retry_job",
            {"id": int(job_id)},
            gbrain_bin=gbrain_bin,
            timeout_ms=timeout_ms,
        ),
        timeout_ms=timeout_ms,
        gbrain_bin=gbrain_bin,
    )


def smoke(
    *,
    gbrain_bin: str = DEFAULT_GBRAIN_BIN,
    timeout_ms: int = DEFAULT_JOBS_TIMEOUT_MS,
) -> Dict[str, Any]:
    command = [gbrain_bin, "jobs", "smoke"]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(0.1, timeout_ms / 1000.0),
            check=False,
        )
        error = None
    except FileNotFoundError:
        completed = None
        error = f"gbrain binary not found: {gbrain_bin}"
        returncode = 127
        stdout = ""
        stderr = ""
    except subprocess.TimeoutExpired as e:
        completed = None
        error = f"gbrain jobs smoke timed out after {timeout_ms}ms"
        returncode = 124
        stdout = e.stdout or ""
        stderr = e.stderr or ""

    duration_ms = int((time.perf_counter() - started) * 1000)
    if completed is not None:
        returncode = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if returncode != 0 and error is None:
            error = _truncate(stderr or stdout or "gbrain jobs smoke failed")

    return {
        "kind": f"{JOBS_SCHEMA_PREFIX}.smoke.v0",
        "ok": error is None and returncode == 0,
        "phase2_allowed_job": PHASE2_ALLOWED_JOB_NAME,
        "gbrain_bin": gbrain_bin,
        "timeout_ms": int(timeout_ms),
        "duration_ms": duration_ms,
        "command": command,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
    }


def _jobs_result(*, action: str, call_result: GBrainCallResult, timeout_ms: int, gbrain_bin: str) -> Dict[str, Any]:
    payload = call_result.payload
    return {
        "kind": f"{JOBS_SCHEMA_PREFIX}.{action}.v0",
        "ok": bool(call_result.ok),
        "phase2_allowed_job": PHASE2_ALLOWED_JOB_NAME,
        "gbrain_bin": gbrain_bin,
        "timeout_ms": int(timeout_ms),
        "duration_ms": int(call_result.duration_ms),
        "command": list(call_result.command),
        "returncode": int(call_result.returncode),
        "result": payload,
        "error": call_result.error,
    }
