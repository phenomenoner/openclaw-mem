function redactSensitiveText(text) {
  if (!text) return text;

  const patterns = [
    [/\bsk-[A-Za-z0-9]{16,}\b/g, "sk-[REDACTED]"],
    [/\bsk-proj-[A-Za-z0-9\-_]{16,}\b/g, "sk-proj-[REDACTED]"],
    [/\bBearer\s+[A-Za-z0-9\-_.=]{8,}\b/g, "Bearer [REDACTED]"],
    [/\bAuthorization:\s*Bearer\s+[A-Za-z0-9\-_.=]{8,}\b/gi, "Authorization: Bearer [REDACTED]"],
    [/\bgh[pousr]_[A-Za-z0-9]{20,}\b/g, "[GITHUB_TOKEN_REDACTED]"],
    [/\bgithub_pat_[A-Za-z0-9_]{20,}\b/g, "[GITHUB_TOKEN_REDACTED]"],
    [/\baws[_-]?secret[_-]?access[_-]?key\b\s*[:=]\s*[A-Za-z0-9/+=]{20,}\b/gi, "aws_secret_access_key=[REDACTED]"],
    [/\b\d{8,12}:[A-Za-z0-9_-]{20,}\b/g, "[TELEGRAM_BOT_TOKEN_REDACTED]"],
    [/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]"],
    [/(?<!\d)(?:\+?\d[\d\-\s()]{7,}\d)(?!\d)/g, "[REDACTED_PHONE]"],
  ];

  let out = text;
  for (const [re, rep] of patterns) out = out.replace(re, rep);
  return out;
}

function extractSummary(message, redactSensitive) {
  if (!message || !message.content) return "";

  try {
    const content = Array.isArray(message.content) ? message.content : [message.content];
    const textParts = content
      .filter((c) => c.type === "text")
      .map((c) => c.text || "")
      .join(" ");

    const summary = textParts.slice(0, 200).trim();
    return redactSensitive ? redactSensitiveText(summary) : summary;
  } catch {
    return "";
  }
}

function shortText(text, maxLength) {
  if (!text) return "";
  return text.length <= maxLength ? text : `${text.slice(0, maxLength)}…`;
}

export function buildToolResultSummary(toolName, message, redactSensitive, maxLength) {
  const raw = extractSummary(message, redactSensitive);
  const compact = raw.replace(/\s+/g, " ").trim();
  if (!compact) return `${toolName} result captured`;
  if (compact.startsWith("{") || compact.startsWith("[")) return `${toolName} result captured`;
  if (/(stdout|stderr|traceback|stack\s*trace|command output)/i.test(compact)) {
    return `${toolName} result captured (output redacted)`;
  }
  return shortText(`${toolName}: ${compact}`, maxLength);
}
