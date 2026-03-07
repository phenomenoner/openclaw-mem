function tierNameFromBucket(bucket) {
  const raw = bucket?.plan?.tier ?? bucket?.tier;
  return typeof raw === 'string' ? raw : '';
}

function compareWildcardCandidates(a, b) {
  if (b.hit.score !== a.hit.score) return b.hit.score - a.hit.score;
  const idDiff = a.hit.row.id.localeCompare(b.hit.row.id);
  if (idDiff !== 0) return idDiff;
  return a.tier.localeCompare(b.tier);
}

export function selectTierQuotaV1(input) {
  const selected = [];
  const seen = new Set();
  const selectedByTier = {};

  const bucketByTier = new Map();
  for (const bucket of input.buckets) {
    const tier = tierNameFromBucket(bucket);
    if (!tier) continue;
    bucketByTier.set(tier, bucket);
  }

  const mustCandidates = bucketByTier.get('must')?.fused.length ?? 0;
  const niceCandidates = bucketByTier.get('nice')?.fused.length ?? 0;
  const unknownCandidates = bucketByTier.get('unknown')?.fused.length ?? 0;

  const niceTarget = Math.min(input.quotas.niceMin, input.limit, niceCandidates);
  const mustTarget = Math.min(input.quotas.mustMax, Math.max(0, input.limit - niceTarget), mustCandidates);
  const unknownTarget = Math.min(
    input.quotas.unknownMax,
    Math.max(0, input.limit - niceTarget - mustTarget),
    unknownCandidates,
  );

  const takeFromTier = (tierName, count) => {
    if (count <= 0 || selected.length >= input.limit) return;

    const bucket = bucketByTier.get(tierName);
    if (!bucket) return;

    let taken = 0;
    for (const hit of bucket.fused) {
      if (taken >= count || selected.length >= input.limit) break;
      if (seen.has(hit.row.id)) continue;
      seen.add(hit.row.id);
      selected.push(hit);
      taken += 1;
      selectedByTier[tierName] = (selectedByTier[tierName] ?? 0) + 1;
    }
  };

  takeFromTier('must', mustTarget);
  takeFromTier('nice', niceTarget);
  takeFromTier('unknown', unknownTarget);

  const wildcardPool = [];
  for (const bucket of input.buckets) {
    const tier = tierNameFromBucket(bucket);
    if (!tier) continue;

    for (const hit of bucket.fused) {
      if (seen.has(hit.row.id)) continue;
      wildcardPool.push({ tier, hit });
    }
  }

  wildcardPool.sort(compareWildcardCandidates);

  let wildcardUsed = 0;
  for (const candidate of wildcardPool) {
    if (selected.length >= input.limit) break;
    if (seen.has(candidate.hit.row.id)) continue;
    seen.add(candidate.hit.row.id);
    selected.push(candidate.hit);
    selectedByTier[candidate.tier] = (selectedByTier[candidate.tier] ?? 0) + 1;
    wildcardUsed += 1;
  }

  return {
    selected,
    selectedByTier,
    quota: {
      mustMax: input.quotas.mustMax,
      niceMin: input.quotas.niceMin,
      unknownMax: input.quotas.unknownMax,
      wildcardUsed,
    },
  };
}

export async function runTierFirstV1(input) {
  const selected = [];
  const seen = new Set();
  const tierCounts = [];
  const ftsResults = [];
  const vecResults = [];
  const rejected = [];

  for (const plan of input.plans) {
    const { ftsResults: tierFts, vecResults: tierVec } = await input.search({
      query: input.query,
      scope: input.scope,
      labels: plan.labels,
      searchLimit: input.searchLimit,
    });

    ftsResults.push(...tierFts);
    vecResults.push(...tierVec);

    const fused = input.fuseRecall({ vector: tierVec, fts: tierFts, limit: input.searchLimit }).order;

    let added = 0;
    for (const hit of fused) {
      if (selected.length >= input.limit) break;
      if (seen.has(hit.row.id)) continue;
      seen.add(hit.row.id);
      selected.push(hit);
      added += 1;
    }

    tierCounts.push({
      tier: plan.tier,
      labels: plan.labels,
      candidates: fused.length,
      selected: added,
    });

    if (fused.length === 0 && plan.missReason) {
      rejected.push(plan.missReason);
    }

    if (selected.length >= input.limit) {
      rejected.push('budget_cap');
      break;
    }
  }

  return {
    selected,
    tierCounts,
    ftsResults,
    vecResults,
    rejected,
  };
}
