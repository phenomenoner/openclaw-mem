export const MS_PER_HOUR = 60 * 60 * 1000;
export const MS_PER_DAY = 24 * MS_PER_HOUR;

function normalizePositiveInteger(value, fallback = 1) {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return fallback;
  const floored = Math.floor(n);
  if (floored < 1) return 1;
  return floored;
}

export function todoDedupeCutoffMs(nowMs, dedupeWindowHours) {
  const safeNow = Number.isFinite(nowMs) ? nowMs : Date.now();
  const windowHours = normalizePositiveInteger(dedupeWindowHours, 1);
  return safeNow - windowHours * MS_PER_HOUR;
}

export function isTodoWithinDedupeWindow(createdAt, nowMs, dedupeWindowHours) {
  const ts = typeof createdAt === 'number' ? createdAt : Number(createdAt);
  if (!Number.isFinite(ts) || ts <= 0) return false;
  return ts >= todoDedupeCutoffMs(nowMs, dedupeWindowHours);
}

export function todoStaleCutoffMs(nowMs, ttlDays) {
  const safeNow = Number.isFinite(nowMs) ? nowMs : Date.now();
  const windowDays = normalizePositiveInteger(ttlDays, 1);
  return safeNow - windowDays * MS_PER_DAY;
}

export function isTodoStale(createdAt, nowMs, ttlDays) {
  const ts = typeof createdAt === 'number' ? createdAt : Number(createdAt);
  if (!Number.isFinite(ts) || ts <= 0) return false;
  return ts < todoStaleCutoffMs(nowMs, ttlDays);
}
