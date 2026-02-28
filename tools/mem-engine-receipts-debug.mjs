#!/usr/bin/env node

import { __debugReceipts } from "../extensions/openclaw-mem-engine/index.ts";

const cfg = __debugReceipts.resolveReceiptsConfig({
  enabled: true,
  verbosity: "low",
  maxItems: 3,
});

const mockRecallResults = [
  {
    row: {
      id: "11111111-1111-1111-1111-111111111111",
      text: "",
      createdAt: 0,
      category: "decision",
      importance: 0.9,
      importance_label: "must_remember",
      scope: "demo",
      trust_tier: "user",
    },
    distance: 0.12,
    score: 0.94,
  },
  {
    row: {
      id: "22222222-2222-2222-2222-222222222222",
      text: "",
      createdAt: 0,
      category: "preference",
      importance: 0.77,
      importance_label: "nice_to_have",
      scope: "demo",
      trust_tier: "user",
    },
    distance: 0.21,
    score: 0.89,
  },
];

const recallReceipt = __debugReceipts.buildRecallLifecycleReceipt({
  cfg,
  skipped: false,
  scope: "demo",
  scopeMode: "explicit",
  rejected: ["budget_cap"],
  tierCounts: [
    { tier: "must", labels: ["must_remember"], candidates: 2, selected: 1 },
    { tier: "nice", labels: ["nice_to_have"], candidates: 1, selected: 1 },
  ],
  ftsResults: mockRecallResults,
  vecResults: mockRecallResults,
  fusedResults: mockRecallResults,
  injectedCount: 2,
});

const autoCaptureReceipt = __debugReceipts.buildAutoCaptureLifecycleReceipt({
  cfg,
  candidateExtractionCount: 6,
  filteredOut: {
    tool_output: 2,
    secrets_like: 1,
    duplicate: 1,
  },
  storedCount: 2,
});

console.log("# recall receipt");
console.log(JSON.stringify(recallReceipt, null, 2));
console.log("\n# autoCapture receipt");
console.log(JSON.stringify(autoCaptureReceipt, null, 2));
