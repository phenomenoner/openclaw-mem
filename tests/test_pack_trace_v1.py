import json
import unittest

from openclaw_mem import pack_trace_v1


class TestPackTraceV1(unittest.TestCase):
    def test_to_dict_is_json_safe_and_has_expected_shape(self):
        trace = pack_trace_v1.PackTraceV1(
            kind=pack_trace_v1.PACK_TRACE_V1_KIND,
            ts="2026-03-03T00:00:00+00:00",
            version=pack_trace_v1.PackTraceV1Version(openclaw_mem="0.0.0"),
            query=pack_trace_v1.PackTraceV1Query(text="hello"),
            budgets=pack_trace_v1.PackTraceV1Budgets(
                budgetTokens=100,
                maxItems=3,
                maxL2Items=0,
                niceCap=100,
            ),
            lanes=[
                pack_trace_v1.PackTraceV1Lane(
                    name="warm",
                    source="sqlite-observations",
                    searched=True,
                    retrievers=[pack_trace_v1.PackTraceV1Retriever(kind="fts5", topK=10)],
                )
            ],
            candidates=[
                pack_trace_v1.PackTraceV1Candidate(
                    id="obs:1",
                    layer="L1",
                    importance="unknown",
                    trust="unknown",
                    scores=pack_trace_v1.PackTraceV1CandidateScores(rrf=0.1, fts=1.0, semantic=0.0),
                    decision=pack_trace_v1.PackTraceV1Decision(
                        included=True,
                        reason=["within_budget"],
                        rationale=["within_budget"],
                        caps=pack_trace_v1.PackTraceV1DecisionCaps(niceCapHit=False, l2CapHit=False),
                    ),
                    citations=pack_trace_v1.PackTraceV1CandidateCitations(url=None, recordRef="obs:1"),
                )
            ],
            output=pack_trace_v1.PackTraceV1Output(
                includedCount=1,
                excludedCount=0,
                l2IncludedCount=0,
                citationsCount=1,
                refreshedRecordRefs=["obs:1"],
                coverage=pack_trace_v1.PackTraceV1Coverage(
                    rationaleMissingCount=0,
                    citationMissingCount=0,
                    allIncludedHaveRationale=True,
                    allIncludedHaveCitations=True,
                ),
            ),
            timing=pack_trace_v1.PackTraceV1Timing(durationMs=5),
        )

        out = pack_trace_v1.to_dict(trace)

        # Basic contract checks (shape + stable kind).
        self.assertEqual(out.get("kind"), pack_trace_v1.PACK_TRACE_V1_KIND)
        self.assertIn("version", out)
        self.assertIn("query", out)
        self.assertIn("budgets", out)
        self.assertIn("lanes", out)
        self.assertIn("candidates", out)
        self.assertIn("output", out)
        self.assertIn("timing", out)

        # Must be JSON-serializable without custom encoders.
        json.dumps(out)


if __name__ == "__main__":
    unittest.main()
