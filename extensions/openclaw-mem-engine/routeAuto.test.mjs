import test from "node:test";
import assert from "node:assert/strict";

import { renderRouteAutoText, runRouteAuto } from "./routeAuto.js";

test("renderRouteAutoText summarizes graph route candidates", () => {
  const text = renderRouteAutoText(
    {
      selection: {
        selected_lane: "graph_match",
        reason: "graph_ready_with_candidates",
        graph_consumption: { preferredCardRefs: ["obs:99"], coveredRawRefs: ["obs:1", "obs:2"] },
      },
      inputs: {
        graph_match: {
          result: {
            candidates: [
              {
                title: "openclaw-mem",
                why_relevant: "matched graph evidence for autonomous routing",
                graph_consumption: {
                  preferredCardRefs: ["obs:99"],
                  coveredRawRefs: ["obs:1", "obs:2"],
                  cards: [{ recordRef: "obs:99", title: "Route auto synthesis card", whyItMatters: "Prefer one maintained synthesis card." }],
                },
              },
              { title: "openclaw-ops", why_relevant: "secondary candidate" },
            ],
          },
        },
      },
    },
    { maxChars: 320, maxGraphCandidates: 1 },
  );

  assert.match(text, /graph-semantic/);
  assert.match(text, /openclaw-mem/);
  assert.match(text, /prefer synthesis Route auto synthesis card over 2 covered raw refs/i);
  assert.doesNotMatch(text, /openclaw-ops/);
});

test("runRouteAuto builds transcript hint block from fake runner", async () => {
  const payload = {
    selection: { selected_lane: "episodes_search", reason: "graph_unready_or_empty_and_transcript_hits_present" },
    inputs: {
      episodes_search: {
        result: {
          sessions: [
            { session_id: "sess-1234567890abcdef", summary: "Need to revisit the readiness bridge and transcript recall" },
          ],
        },
      },
    },
  };

  const result = await runRouteAuto({
    query: "readiness bridge",
    scope: "openclaw-mem",
    config: { enabled: true, timeoutMs: 500, maxTranscriptSessions: 1, maxChars: 240 },
    runner: async ({ command, args, timeoutMs }) => {
      assert.equal(command, "openclaw-mem");
      assert.equal(args[0], "--json");
      assert.equal(args[1], "route");
      assert.equal(args[2], "auto");
      assert.equal(args[3], "readiness bridge");
      assert.equal(args[4], "--scope");
      assert.equal(args[5], "openclaw-mem");
      assert.equal(timeoutMs, 500);
      return { ok: true, exitCode: 0, stdout: JSON.stringify(payload), stderr: "", errorCode: null, errorMessage: null };
    },
  });

  assert.equal(result.receipt.selectedLane, "episodes_search");
  assert.equal(result.receipt.injected, true);
  assert.match(result.text, /transcript recall/);
  assert.match(result.text, /sess-1234567890abc/);
});

test("runRouteAuto receipt carries synthesis coverage counts", async () => {
  const payload = {
    selection: {
      selected_lane: "graph_match",
      reason: "graph_ready_with_candidates",
      graph_consumption: {
        preferredCardRefs: ["obs:99"],
        coveredRawRefs: ["obs:1", "obs:2"],
      },
    },
    inputs: {
      graph_match: {
        result: {
          candidates: [
            {
              title: "openclaw-mem",
              why_relevant: "matched graph evidence",
              graph_consumption: {
                preferredCardRefs: ["obs:99"],
                coveredRawRefs: ["obs:1", "obs:2"],
                cards: [{ recordRef: "obs:99", title: "Route auto synthesis card" }],
              },
            },
          ],
        },
      },
    },
  };

  const result = await runRouteAuto({
    query: "graph semantic memory",
    scope: "global",
    config: { enabled: true, timeoutMs: 400, maxChars: 320 },
    runner: async () => ({ ok: true, exitCode: 0, stdout: JSON.stringify(payload), stderr: "", errorCode: null, errorMessage: null }),
  });

  assert.equal(result.receipt.selectedLane, "graph_match");
  assert.equal(result.receipt.preferredCardCount, 1);
  assert.equal(result.receipt.coveredRawRefCount, 2);
  assert.deepEqual(result.receipt.preferredCardRefs, ["obs:99"]);
  assert.match(result.text, /prefer synthesis Route auto synthesis card/i);
});

test("runRouteAuto fails open on runner error", async () => {
  const result = await runRouteAuto({
    query: "graph semantic memory",
    scope: "global",
    config: { enabled: true, timeoutMs: 250 },
    runner: async () => ({
      ok: false,
      exitCode: null,
      stdout: "",
      stderr: "",
      errorCode: "ENOENT",
      errorMessage: "openclaw-mem not found",
    }),
  });

  assert.equal(result.text, "");
  assert.equal(result.receipt.selectedLane, "none");
  assert.equal(result.receipt.injected, false);
  assert.equal(result.receipt.errorCode, "ENOENT");
});
