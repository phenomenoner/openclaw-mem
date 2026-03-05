export const MS_PER_HOUR = 60 * 60 * 1000;
export const MS_PER_DAY = 24 * MS_PER_HOUR;

export function todoDedupeCutoffMs(nowMs, dedupeWindowHours) {
  const safeNow = Number.isFinite(nowMs) ? nowMs : Date.now();
  const windowHours = Math.max(1, Math.floor(dedupeWindowHours));
  return safeNow - windowHours * MS_PER_HOUR;
}

export function isTodoWithinDedupeWindow(createdAt, nowMs, dedupeWindowHours) {
  const ts = typeof createdAt === 'number' ? createdAt : Number(createdAt);
  if (!Number.isFinite(ts) || ts <= 0) return false;
  return ts >= todoDedupeCutoffMs(nowMs, dedupeWindowHours);
}

export function todoStaleCutoffMs(nowMs, ttlDays) {
  const safeNow = Number.isFinite(nowMs) ? nowMs : Date.now();
  const windowDays = Math.max(1, Math.floor(ttlDays));
  return safeNow - windowDays * MS_PER_DAY;
}

export function isTodoStale(createdAt, nowMs, ttlDays) {
  const ts = typeof createdAt === 'number' ? createdAt : Number(createdAt);
  if (!Number.isFinite(ts) || ts <= 0) return false;
  return ts < todoStaleCutoffMs(nowMs, ttlDays);
}
