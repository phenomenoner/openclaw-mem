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

export const OUTPUT_FIELD_KEYS = Object.freeze(["stdout", "stderr", "raw_stdout", "raw_stderr", "tool_output", "command_output"]);
const OUTPUT_FIELD_KEY_SET = new Set(OUTPUT_FIELD_KEYS);

function hasStructuredOutputFields(value, depth = 0) {
  if (depth > 5 || value == null) return false;

  if (Array.isArray(value)) {
    return value.some((item) => hasStructuredOutputFields(item, depth + 1));
  }

  if (typeof value === "object") {
    for (const [k, v] of Object.entries(value)) {
      const key = String(k || "").toLowerCase().trim();
      if (OUTPUT_FIELD_KEYS.includes(key)) {
        return true;
      }
      if (hasStructuredOutputFields(v, depth + 1)) {
        return true;
      }
    }
  }

  return false;
}

function hasJsonLikeOutputFieldKey(text) {
  if (!text) return false;

  const source = String(text);
  const stack = [];

  const skipWhitespace = (index) => {
    let cursor = index;
    while (cursor < source.length && /\s/.test(source[cursor])) cursor += 1;
    return cursor;
  };

  const parseQuoted = (index) => {
    const quote = source[index];
    let cursor = index + 1;
    let escaped = false;
    let token = "";

    while (cursor < source.length) {
      const ch = source[cursor];
      if (escaped) {
        token += ch;
        escaped = false;
        cursor += 1;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        cursor += 1;
        continue;
      }
      if (ch === quote) {
        return { token, next: cursor + 1 };
      }
      token += ch;
      cursor += 1;
    }

    return { token, next: cursor };
  };

  const parseBare = (index) => {
    let cursor = index;
    while (cursor < source.length && !/[\s{}\[\],:]/.test(source[cursor])) cursor += 1;
    return { token: source.slice(index, cursor), next: cursor };
  };

  const pushContext = (type, returnState = null) => {
    stack.push({
      type,
      state: type === "object" ? "expect_key_or_end" : "expect_value_or_end",
      pendingKey: "",
      returnState,
    });
  };

  const closeContext = () => {
    const closed = stack.pop();
    if (!closed || closed.returnState == null) return;
    const parent = stack[stack.length - 1];
    if (parent) parent.state = closed.returnState;
  };

  let cursor = 0;
  while (cursor < source.length) {
    cursor = skipWhitespace(cursor);
    if (cursor >= source.length) break;

    const context = stack[stack.length - 1];
    const ch = source[cursor];

    if (!context) {
      if (ch === "{") {
        pushContext("object");
        cursor += 1;
        continue;
      }
      if (ch === "[") {
        pushContext("array");
        cursor += 1;
        continue;
      }
      cursor += 1;
      continue;
    }

    if (context.type === "object") {
      if (context.state === "expect_key_or_end") {
        if (ch === "}") {
          closeContext();
          cursor += 1;
          continue;
        }
        if (ch === ",") {
          cursor += 1;
          continue;
        }
        if (ch === '"' || ch === "'") {
          const parsed = parseQuoted(cursor);
          context.pendingKey = parsed.token.toLowerCase().trim();
          context.state = "expect_colon";
          cursor = parsed.next;
          continue;
        }
        if (!/[{}\[\],:]/.test(ch)) {
          const parsed = parseBare(cursor);
          context.pendingKey = parsed.token.toLowerCase().trim();
          context.state = "expect_colon";
          cursor = parsed.next;
          continue;
        }
        cursor += 1;
        continue;
      }

      if (context.state === "expect_colon") {
        if (ch === ":") {
          if (OUTPUT_FIELD_KEY_SET.has(context.pendingKey)) {
            return true;
          }
          context.state = "expect_value";
          cursor += 1;
          continue;
        }
        if (ch === ",") {
          context.state = "expect_key_or_end";
          cursor += 1;
          continue;
        }
        if (ch === "}") {
          closeContext();
          cursor += 1;
          continue;
        }
        cursor += 1;
        continue;
      }

      if (context.state === "expect_value") {
        if (ch === "{") {
          pushContext("object", "expect_comma_or_end");
          cursor += 1;
          continue;
        }
        if (ch === "[") {
          pushContext("array", "expect_comma_or_end");
          cursor += 1;
          continue;
        }
        if (ch === '"' || ch === "'") {
          const parsed = parseQuoted(cursor);
          context.state = "expect_comma_or_end";
          cursor = parsed.next;
          continue;
        }
        if (!/[{}\[\],:]/.test(ch)) {
          const parsed = parseBare(cursor);
          context.state = "expect_comma_or_end";
          cursor = parsed.next;
          continue;
        }
        if (ch === "}") {
          closeContext();
          cursor += 1;
          continue;
        }
        cursor += 1;
        continue;
      }

      if (ch === ",") {
        context.state = "expect_key_or_end";
        cursor += 1;
        continue;
      }
      if (ch === "}") {
        closeContext();
        cursor += 1;
        continue;
      }
      cursor += 1;
      continue;
    }

    if (context.state === "expect_value_or_end") {
      if (ch === "]") {
        closeContext();
        cursor += 1;
        continue;
      }
      if (ch === "{") {
        pushContext("object", "expect_comma_or_end");
        cursor += 1;
        continue;
      }
      if (ch === "[") {
        pushContext("array", "expect_comma_or_end");
        cursor += 1;
        continue;
      }
      if (ch === '"' || ch === "'") {
        const parsed = parseQuoted(cursor);
        context.state = "expect_comma_or_end";
        cursor = parsed.next;
        continue;
      }
      if (!/[{}\[\],:]/.test(ch)) {
        const parsed = parseBare(cursor);
        context.state = "expect_comma_or_end";
        cursor = parsed.next;
        continue;
      }
      cursor += 1;
      continue;
    }

    if (ch === ",") {
      context.state = "expect_value_or_end";
      cursor += 1;
      continue;
    }
    if (ch === "]") {
      closeContext();
      cursor += 1;
      continue;
    }
    cursor += 1;
  }

  return false;
}

export function buildToolResultSummary(toolName, message, redactSensitive, maxLength) {
  const raw = extractSummary(message, redactSensitive);
  const compact = raw.replace(/\s+/g, " ").trim();
  if (!compact) return `${toolName} result captured`;

  if (compact.startsWith("{") || compact.startsWith("[")) {
    let parsed;
    try {
      parsed = JSON.parse(compact);
    } catch {
      parsed = undefined;
    }

    const structuredOutputHint = parsed !== undefined
      ? hasStructuredOutputFields(parsed)
      : hasJsonLikeOutputFieldKey(compact);

    if (structuredOutputHint) {
      return `${toolName} result captured (output redacted)`;
    }

    return shortText(`${toolName}: ${compact}`, maxLength);
  }

  if (/(?:^|[\s([{,;])(?:stdout|stderr|raw_stdout|raw_stderr|tool_output|command_output)\s*:/i.test(compact)) {
    return `${toolName} result captured (output redacted)`;
  }
  if (/(traceback|stack\s*trace|command output)/i.test(compact)) {
    return `${toolName} result captured (output redacted)`;
  }
  return shortText(`${toolName}: ${compact}`, maxLength);
}
