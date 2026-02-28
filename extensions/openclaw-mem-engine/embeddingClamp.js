// Utilities for clamping embedding inputs and classifying provider errors.
// Plain JS (no TS syntax) so it can be exercised with `node --test`.

import { Buffer } from "node:buffer";

export const DEFAULT_EMBEDDING_MAX_CHARS = 6000;
export const DEFAULT_EMBEDDING_HEAD_CHARS = 500;
export const CLIP_MARKER = "\n...\n";

export function resolveEmbeddingClampConfig(rawEmbedding) {
  const raw = rawEmbedding && typeof rawEmbedding === "object" ? rawEmbedding : {};

  const maxChars = clampInt(raw.maxChars, DEFAULT_EMBEDDING_MAX_CHARS, { min: 200, max: 200_000 });
  const headChars = clampInt(raw.headChars, DEFAULT_EMBEDDING_HEAD_CHARS, { min: 0, max: maxChars });

  // maxBytes is optional. If set, it is applied after maxChars.
  const maxBytesRaw = raw.maxBytes;
  const maxBytes =
    typeof maxBytesRaw === "number" && Number.isFinite(maxBytesRaw) && maxBytesRaw > 0
      ? Math.floor(maxBytesRaw)
      : typeof maxBytesRaw === "string"
        ? parsePositiveInt(maxBytesRaw)
        : undefined;

  return {
    maxChars,
    headChars: Math.min(headChars, maxChars),
    maxBytes,
  };
}

function parsePositiveInt(raw) {
  const n = Number(String(raw).trim());
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.floor(n);
}

function clampInt(raw, fallback, { min, max }) {
  const n = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw.trim()) : Number.NaN;
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.floor(n)));
}

function byteLen(text) {
  return Buffer.byteLength(String(text ?? ""), "utf8");
}

function sliceTailByChars(input, n) {
  const s = String(input ?? "");
  if (n <= 0) return "";
  if (s.length <= n) return s;
  return s.slice(s.length - n);
}

function sliceHeadByChars(input, n) {
  const s = String(input ?? "");
  if (n <= 0) return "";
  if (s.length <= n) return s;
  return s.slice(0, n);
}

function clampTailToMaxBytes(tail, maxBytes) {
  // Deterministic: keep as much of the tail as fits.
  const s = String(tail ?? "");
  if (!maxBytes || maxBytes <= 0) return s;
  if (byteLen(s) <= maxBytes) return s;

  let lo = 0;
  let hi = s.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    const candidate = sliceTailByChars(s, mid);
    if (byteLen(candidate) <= maxBytes) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return sliceTailByChars(s, lo);
}

function clampHeadToMaxBytes(head, maxBytes) {
  // Deterministic: keep as much of the head as fits.
  const s = String(head ?? "");
  if (!maxBytes || maxBytes <= 0) return s;
  if (byteLen(s) <= maxBytes) return s;

  let lo = 0;
  let hi = s.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    const candidate = sliceHeadByChars(s, mid);
    if (byteLen(candidate) <= maxBytes) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return sliceHeadByChars(s, lo);
}

export function clampEmbeddingInput(input, cfg) {
  const text = String(input ?? "");
  const maxChars = Math.max(1, Math.floor(cfg?.maxChars ?? DEFAULT_EMBEDDING_MAX_CHARS));
  const headChars = Math.max(0, Math.min(Math.floor(cfg?.headChars ?? DEFAULT_EMBEDDING_HEAD_CHARS), maxChars));
  const maxBytes = typeof cfg?.maxBytes === "number" && Number.isFinite(cfg.maxBytes) && cfg.maxBytes > 0 ? Math.floor(cfg.maxBytes) : undefined;

  const originalChars = text.length;
  const originalBytes = byteLen(text);

  let out = text;
  let clipped = false;

  if (out.length > maxChars) {
    clipped = true;

    if (headChars <= 0) {
      out = sliceTailByChars(out, maxChars);
    } else {
      const head = sliceHeadByChars(out, headChars);
      const budget = maxChars - head.length - CLIP_MARKER.length;
      if (budget <= 0) {
        out = sliceHeadByChars(head, maxChars);
      } else {
        const tail = sliceTailByChars(out, budget);
        out = `${head}${CLIP_MARKER}${tail}`;
      }
    }
  }

  if (maxBytes && byteLen(out) > maxBytes) {
    clipped = true;

    if (headChars <= 0 || !out.includes(CLIP_MARKER)) {
      out = clampTailToMaxBytes(out, maxBytes);
    } else {
      const [headPart, tailPart] = out.split(CLIP_MARKER, 2);
      const head = clampHeadToMaxBytes(headPart, Math.max(0, maxBytes - Math.min(maxBytes, byteLen(CLIP_MARKER))));
      const remaining = Math.max(0, maxBytes - byteLen(head) - byteLen(CLIP_MARKER));
      const tail = clampTailToMaxBytes(tailPart ?? "", remaining);

      // If even head doesn't fit with marker, degrade to just head.
      if (byteLen(head) > maxBytes) {
        out = clampHeadToMaxBytes(head, maxBytes);
      } else if (byteLen(head) + byteLen(CLIP_MARKER) > maxBytes || remaining <= 0) {
        out = head;
      } else {
        out = `${head}${CLIP_MARKER}${tail}`;
      }
    }
  }

  // Final defensive trim by chars (should already hold).
  if (out.length > maxChars) {
    clipped = true;
    out = sliceTailByChars(out, maxChars);
  }

  return {
    text: out,
    clipped,
    originalChars,
    clampedChars: out.length,
    originalBytes,
    clampedBytes: byteLen(out),
    maxChars,
    headChars,
    maxBytes: maxBytes ?? null,
  };
}

export class EmbeddingInputTooLongError extends Error {
  constructor(message, info) {
    super(message);
    this.name = "EmbeddingInputTooLongError";
    this.code = "embedding_input_too_long";
    this.info = info ?? null;
  }
}

export function isEmbeddingInputTooLongError(err) {
  if (!err) return false;
  if (err instanceof EmbeddingInputTooLongError) return true;
  const anyErr = err;
  return anyErr.code === "embedding_input_too_long" || anyErr.name === "EmbeddingInputTooLongError";
}

export function looksLikeEmbeddingInputTooLongMessage(bodyText) {
  const body = String(bodyText ?? "");
  if (!body) return false;
  return (
    /maximum context length/i.test(body) ||
    /max context length/i.test(body) ||
    /requested\s+\d+\s+tokens/i.test(body) ||
    /Please reduce the length of the messages/i.test(body)
  );
}
