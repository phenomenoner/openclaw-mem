import unittest

from openclaw_mem.provenance_trust_schema import (
    normalize_provenance_kind_counts,
    normalize_trust_tier,
    parse_provenance_ref,
)


class TestProvenanceTrustSchema(unittest.TestCase):
    def test_parse_provenance_ref_file_line(self):
        ref = parse_provenance_ref("docs/topology.yaml#L20-L10")
        self.assertEqual(ref["kind"], "file_line")
        self.assertTrue(ref["is_structured"])
        self.assertEqual(ref["line_start"], 20)
        self.assertEqual(ref["line_end"], 20)

    def test_parse_provenance_ref_url_and_receipt(self):
        self.assertEqual(parse_provenance_ref("https://example.com/x")["kind"], "url")
        self.assertEqual(parse_provenance_ref("receipt:abc")["kind"], "receipt")

    def test_normalize_trust_tier_aliases(self):
        self.assertEqual(normalize_trust_tier("trusted"), "trusted")
        self.assertEqual(normalize_trust_tier("quarantine"), "quarantined")
        self.assertIsNone(normalize_trust_tier("semi-trusted"))

    def test_normalize_provenance_kind_counts_coalesces_unknown(self):
        out = normalize_provenance_kind_counts({"file-line": 2, "manual": 3, "opaque": 1, "none": 0})
        self.assertEqual(out, {"file_line": 2, "opaque": 4})


if __name__ == "__main__":
    unittest.main()
