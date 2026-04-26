import argparse
import json
import tempfile
import unittest
from pathlib import Path

from tools import workingset_multipass_eval as eval_tool


class TestWorkingSetMultipassEval(unittest.TestCase):
    def test_build_bundle_is_isolated_and_blinded(self):
        with tempfile.TemporaryDirectory() as td:
            args = argparse.Namespace(
                out_dir=td,
                run_id="run-test",
                seed="fixed",
                subject_model="openai-codex/gpt-5.2",
                json=True,
            )
            receipt = eval_tool.build_bundle(args)
            self.assertTrue(receipt["ok"])
            run_dir = Path(receipt["out_dir"])
            self.assertTrue((run_dir / "RUN_META.json").exists())
            self.assertTrue((run_dir / "SUBJECT_PACKETS.jsonl").exists())

            meta = json.loads((run_dir / "RUN_META.json").read_text(encoding="utf-8"))
            self.assertFalse(meta["isolation"]["main_chat_history_allowed"])
            self.assertEqual(meta["subject_model"], "openai-codex/gpt-5.2")
            labels = {arm["blind_label"] for arm in meta["arms"].values()}
            self.assertEqual(labels, {"TRANSCRIPTS_A.jsonl", "TRANSCRIPTS_B.jsonl"})
            self.assertEqual(
                meta["output_files"],
                [
                    "RUN_META.json",
                    "CASE_MATRIX.md",
                    "TRANSCRIPTS_A.jsonl",
                    "TRANSCRIPTS_B.jsonl",
                    "TURN_TELEMETRY.jsonl",
                    "BLIND_JUDGE_RESULTS.json",
                    "SUMMARY.md",
                ],
            )
            for name in meta["output_files"]:
                self.assertTrue((run_dir / name).exists(), name)

            packets = [json.loads(line) for line in (run_dir / "SUBJECT_PACKETS.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(packets), len(eval_tool.CASES) * 2)
            self.assertTrue(all(packet["isolation"]["must_not_use_main_chat_history"] for packet in packets))
            self.assertTrue(all(5 <= len(packet["turns"]) <= 8 for packet in packets))

            telemetry = [json.loads(line) for line in (run_dir / "TURN_TELEMETRY.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(telemetry), sum(len(case["turns"]) for case in eval_tool.CASES) * 2)
            required = {
                "turn_index",
                "arm_id",
                "workingSetEnabled",
                "visibleContextTokenCount",
                "workingSetTokenCount",
                "workingSetIds",
                "alreadyVisibleIds",
                "dedupedWorkingSetIds",
                "repeatedAcrossTurnsCount",
                "taskSpecificRecallIds",
                "evictedHigherPrecisionRecallCount",
                "budgetPressureReason",
                "answerTokenCount",
            }
            self.assertTrue(required.issubset(telemetry[0]))

            judge = json.loads((run_dir / "BLIND_JUDGE_PACKET.json").read_text(encoding="utf-8"))
            self.assertIn("arm_id", judge["judge_must_not_see"])
            self.assertIn("RUN_META.arms", judge["judge_must_not_see"])
            self.assertIn("TURN_TELEMETRY.jsonl", meta["private_files_not_for_judge"])
            self.assertNotIn("baseline_off", json.dumps(judge))
            self.assertNotIn("candidate_on", json.dumps(judge))
            judge_bundle = run_dir / "JUDGE_BUNDLE"
            self.assertTrue((judge_bundle / "BLIND_JUDGE_PACKET.json").exists())
            self.assertFalse((judge_bundle / "RUN_META.json").exists())
            self.assertFalse((judge_bundle / "TURN_TELEMETRY.jsonl").exists())

    def test_blind_arm_map_is_deterministic_per_run_id(self):
        self.assertEqual(eval_tool.blind_arm_map("same"), eval_tool.blind_arm_map("same"))

    def test_subject_packet_and_telemetry_keys_are_contract_enforced(self):
        case = eval_tool.CASES[0]
        packet = eval_tool.subject_packet(case, arm_id="baseline_off", working_set_enabled=False, model="model")
        packet["blind_label"] = "TRANSCRIPTS_A.jsonl"
        eval_tool._assert_allowed_keys("subject packet", packet, eval_tool.SUBJECT_PACKET_KEYS)
        packet["unsupported"] = True
        with self.assertRaisesRegex(ValueError, "unsupported"):
            eval_tool._assert_allowed_keys("subject packet", packet, eval_tool.SUBJECT_PACKET_KEYS)

        telemetry = eval_tool.telemetry_template(case, arm_id="baseline_off", working_set_enabled=False)[0]
        eval_tool._assert_allowed_keys("turn telemetry", telemetry, eval_tool.TURN_TELEMETRY_KEYS)
        telemetry["extraMetric"] = 1
        with self.assertRaisesRegex(ValueError, "extraMetric"):
            eval_tool._assert_allowed_keys("turn telemetry", telemetry, eval_tool.TURN_TELEMETRY_KEYS)


if __name__ == "__main__":
    unittest.main()
