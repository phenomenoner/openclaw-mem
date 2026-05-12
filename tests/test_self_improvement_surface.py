from __future__ import annotations

import unittest

from openclaw_mem.self_improvement_surface import validate_bundle, validate_inventory, validate_receipt


class TestSelfImprovementSurface(unittest.TestCase):
    def test_valid_inventory_counts_states_and_protected_surfaces(self):
        receipt = validate_inventory(
            {
                "surfaces": [
                    {
                        "surface_id": "goal.primitive",
                        "state": "lab",
                        "owner": "openclaw-mem",
                        "write_authority": "stage",
                        "risk_class": "L1",
                        "protected": False,
                    },
                    {
                        "surface_id": "skills.operator-rule",
                        "state": "stable",
                        "owner": "operator",
                        "write_authority": "none",
                        "risk_class": "L3",
                        "protected": True,
                    },
                ]
            }
        )
        self.assertTrue(receipt["ok"])
        self.assertFalse(receipt["writes_performed"])
        self.assertEqual(receipt["surface_count"], 2)
        self.assertEqual(receipt["protected_count"], 1)
        self.assertEqual(receipt["states"]["lab"], 1)

    def test_invalid_inventory_state_fails(self):
        receipt = validate_inventory(
            {
                "surfaces": [
                    {
                        "surface_id": "bad",
                        "state": "enabled",
                        "write_authority": "stage",
                        "risk_class": "L1",
                    }
                ]
            }
        )
        self.assertFalse(receipt["ok"])
        self.assertIn("state", " ".join(receipt["errors"]))

    def test_protected_surface_requires_sufficient_authority(self):
        inventory = {
            "surfaces": [
                {
                    "surface_id": "skills.operator-rule",
                    "state": "stable",
                    "write_authority": "none",
                    "risk_class": "L3",
                    "protected": True,
                }
            ]
        }
        receipt = {
            "mode": "stage",
            "writes_performed": True,
            "risk_class": "L3",
            "applied": [{"surface_id": "skills.operator-rule", "action": "patch"}],
        }
        result = validate_receipt(receipt, inventory=inventory)
        self.assertFalse(result["ok"])
        self.assertTrue(result["protected_touched"])
        self.assertIn("requiring apply-local", " ".join(result["errors"]))

    def test_protected_surface_can_be_applied_with_sufficient_authority(self):
        inventory = {
            "surfaces": [
                {
                    "surface_id": "skills.operator-rule",
                    "state": "stable",
                    "write_authority": "none",
                    "risk_class": "L3",
                    "protected": True,
                }
            ]
        }
        receipt = {
            "mode": "apply-local",
            "writes_performed": True,
            "risk_class": "L3",
            "applied": [{"surface_id": "skills.operator-rule", "action": "patch"}],
        }
        result = validate_receipt(receipt, inventory=inventory)
        self.assertTrue(result["ok"])
        self.assertTrue(result["protected_touched"])

    def test_l4_surface_requires_apply_publish(self):
        inventory = {
            "surfaces": [
                {
                    "surface_id": "cron.topology",
                    "state": "stable",
                    "write_authority": "apply-local",
                    "risk_class": "L4",
                    "protected": False,
                }
            ]
        }
        receipt = {
            "mode": "apply-local",
            "writes_performed": True,
            "risk_class": "L4",
            "applied": [{"surface_id": "cron.topology", "action": "patch"}],
        }
        result = validate_receipt(receipt, inventory=inventory)
        self.assertFalse(result["ok"])
        self.assertIn("requiring apply-publish", " ".join(result["errors"]))

    def test_non_empty_applied_requires_at_least_suggest(self):
        result = validate_receipt({"mode": "none", "writes_performed": False, "applied": [{"surface_id": "x"}]})
        self.assertFalse(result["ok"])
        self.assertIn("mode >= suggest", " ".join(result["errors"]))

    def test_writes_performed_requires_apply_local(self):
        result = validate_receipt({"mode": "stage", "writes_performed": True, "applied": []})
        self.assertFalse(result["ok"])
        self.assertIn("writes_performed=true", " ".join(result["errors"]))

    def test_unknown_surface_id_warns_not_errors_when_mode_is_sufficient(self):
        result = validate_receipt(
            {"mode": "stage", "writes_performed": False, "applied": [{"surface_id": "unknown"}]},
            inventory={"surfaces": []},
        )
        self.assertTrue(result["ok"])
        self.assertIn("unknown surface_id", " ".join(result["warnings"]))

    def test_bundle_combines_inventory_and_receipt(self):
        inventory = {
            "surfaces": [
                {
                    "surface_id": "goal.primitive",
                    "state": "lab",
                    "write_authority": "stage",
                    "risk_class": "L1",
                    "protected": False,
                }
            ]
        }
        receipt = {"mode": "stage", "writes_performed": False, "applied": []}
        result = validate_bundle(inventory=inventory, receipt=receipt)
        self.assertTrue(result["ok"])
        self.assertFalse(result["writes_performed"])
        self.assertTrue(result["inventory"]["ok"])
        self.assertTrue(result["receipt"]["ok"])


if __name__ == "__main__":
    unittest.main()
