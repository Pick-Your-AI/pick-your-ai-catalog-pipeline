"""Adversarial tests of the planning boundary, using fictional in-memory receipts.

Receipt fixtures exercise shape validation only; they do not represent GitHub
reviews or real decisions. No test performs network access or changes the plan.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from planlib import load_bundle, load_json, validate_bundle, validate_project_config, validate_repository


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = load_bundle(ROOT)

    def setUp(self):
        self.bundle = copy.deepcopy(self.baseline)

    def package(self, identifier):
        return next(p for e in self.bundle["backlog"]["epics"] for p in e["work_packages"] if p["id"] == identifier)

    def assert_error(self, text):
        errors = validate_bundle(self.bundle)
        self.assertTrue(any(text in e for e in errors), f"Missing diagnostic {text!r}; got {errors}")

    def test_repository_schema_and_semantics(self):
        self.assertEqual(validate_repository(ROOT), [])

    def test_semantic_baseline(self):
        self.assertEqual(validate_bundle(self.bundle), [])

    def test_duplicate_task_id_is_not_silently_overwritten(self):
        tasks = self.package("CP-01.01")["tasks"]
        tasks[1]["id"] = tasks[0]["id"]
        self.assert_error("duplicate planning ID")

    def test_duplicate_subtask_id_is_rejected(self):
        subtasks = self.package("CP-01.01")["tasks"][0]["subtasks"]
        subtasks[1]["id"] = subtasks[0]["id"]
        self.assert_error("duplicate planning ID")

    def test_wrong_native_parent_is_rejected(self):
        self.package("CP-01.01")["parent"] = "CP-02"
        self.assert_error("parent must be CP-01")

    def test_empty_epic_cannot_hide_missing_scope(self):
        self.bundle["backlog"]["epics"][0]["work_packages"] = []
        self.assert_error("at least one work package")

    def test_missing_dependency_is_rejected(self):
        self.package("CP-01.02")["blocked_by"].append("CP-99.99")
        self.assert_error("missing or non-native blocked_by target")

    def test_dependency_cycle_is_rejected(self):
        self.package("CP-01.01")["blocked_by"] = ["CP-01.02"]
        self.package("CP-01.01")["dependency_status"] = "Blocked"
        self.assert_error("blocked_by dependency cycle")

    def test_dependency_cannot_be_delivered_in_a_later_phase(self):
        self.package("CP-01.01")["blocked_by"] = ["CP-16.04"]
        self.package("CP-01.01")["dependency_status"] = "Blocked"
        self.assert_error("is in later phase Expansion")

    def test_child_cannot_wait_for_its_own_parent_to_finish(self):
        self.package("CP-01.01")["blocked_by"] = ["CP-01"]
        self.package("CP-01.01")["dependency_status"] = "Blocked"
        self.assert_error("cannot wait on ancestor")

    def test_missing_primary_coverage_is_rejected(self):
        self.bundle["coverage"]["requirements"].pop(0)
        self.assert_error("requires exactly one primary requirement mapping")

    def test_duplicate_coverage_cannot_inflate_completeness(self):
        duplicate = copy.deepcopy(self.bundle["coverage"]["requirements"][0])
        duplicate["id"] = "REQ-99"
        self.bundle["coverage"]["requirements"].append(duplicate)
        self.assert_error("requires exactly one primary requirement mapping (found 2)")

    def test_missing_domain_is_not_allowed_to_shrink_the_ecosystem(self):
        self.bundle["coverage"]["domains"] = [r for r in self.bundle["coverage"]["domains"] if r["domain_id"] != "paper"]
        self.assert_error("missing ecosystem domain paper")

    def test_consumer_reference_must_resolve(self):
        self.bundle["coverage"]["consumer_contracts"][0]["work_packages"].append("CP-88.88")
        self.assert_error("missing work package CP-88.88")

    def test_decision_reference_must_resolve(self):
        self.bundle["decisions"]["decisions"][0]["work_packages"].append("CP-88.88")
        self.assert_error("missing work package CP-88.88")

    def test_duplicate_release_membership_is_rejected(self):
        self.bundle["releases"]["phases"][1]["required_work_packages"].append("CP-01.01")
        self.assert_error("must belong to exactly one phase (found 2)")

    def test_omitted_release_membership_is_rejected(self):
        self.bundle["releases"]["phases"][0]["required_work_packages"].remove("CP-01.01")
        self.assert_error("must belong to exactly one phase (found 0)")

    def test_invalid_phase_is_rejected(self):
        self.package("CP-01.01")["phase"] = "Soon"
        self.assert_error("phase: invalid value")

    def test_unowned_work_cannot_be_ready(self):
        self.package("CP-01.01")["status"] = "Ready"
        self.assert_error("Ready requires an accepted native assignee")

    def test_open_prerequisite_prevents_ready(self):
        package = self.package("CP-01.02")
        package["readiness"] = "Ready"
        package["assignees"] = ["fixture-maintainer"]
        self.assert_error("unresolved prerequisite")

    def test_parent_cannot_finish_with_incomplete_children(self):
        package = self.package("CP-01.01")
        package["status"] = "Done"
        package["acceptance_status"] = "Accepted"
        package["acceptance_receipts"] = [self.receipt()]
        self.assert_error("Done parent has incomplete child")

    def test_task_completion_needs_actual_receipt_shape(self):
        self.package("CP-01.01")["tasks"][0]["done"] = True
        self.assert_error("actual acceptance receipts are required")

    def test_synthetic_receipt_cannot_approve_real_work(self):
        subtask = self.package("CP-01.01")["tasks"][0]["subtasks"][0]
        subtask["done"] = True
        subtask["acceptance_receipts"] = [{**self.receipt(), "synthetic": True}]
        self.assert_error("must explicitly be false for real acceptance")

    def test_real_progress_is_not_forced_back_to_the_bootstrap_baseline(self):
        package = self.package("CP-01.01")
        for task in package["tasks"]:
            for subtask in task["subtasks"]:
                subtask.update(done=True, acceptance_receipts=[self.receipt()])
            task.update(done=True, acceptance_receipts=[self.receipt()])
        package.update(status="Done", acceptance_status="Accepted", assignees=["fixture-maintainer"], acceptance_receipts=[self.receipt()])
        self.assertEqual(validate_bundle(self.bundle), [])
        self.assertEqual(package["status"], "Done")
        self.assertEqual(package["assignees"], ["fixture-maintainer"])

    def test_scope_reconciliation_cannot_reset_progress(self):
        self.bundle["backlog"]["reconciliation"]["reset_existing_progress"] = True
        self.assert_error("reset_existing_progress=false")

    def test_progress_preservation_cannot_drop_assignees(self):
        self.bundle["backlog"]["reconciliation"]["preserve_fields"].remove("assignees")
        self.assert_error("must preserve live assignees")

    def test_bootstrap_cannot_be_promoted_to_real_data(self):
        self.bundle["releases"]["bootstrap"].update(synthetic_only=False, publication_eligible=True, deployed=True, production_record_count=1)
        self.assert_error("bootstrap is not production")
        self.assert_error("production_record_count")

    def test_unknown_coverage_cannot_be_filled_with_invented_zero(self):
        self.bundle["coverage"]["domains"][0]["measurement"]["published"] = 0
        self.assert_error("Planned counts must remain unknown")

    def test_github_number_cannot_be_invented_in_the_scope_baseline(self):
        self.bundle["backlog"]["program"]["issue_number"] = 1
        self.assert_error("require verified readback metadata")

    def test_accepted_decision_requires_attributable_receipts(self):
        self.bundle["decisions"]["decisions"][0].update(status="Accepted", accepted_by=["fixture-maintainer"])
        self.assert_error("actual acceptance receipts are required")

    def test_project_options_cannot_diverge_from_backlog_vocabulary(self):
        config = load_json(ROOT / "planning" / "project-config.json")
        field = next(field for field in config["fields"] if field["name"] == "Release Phase")
        field["options"].append("Soon")
        errors = validate_project_config(config, self.bundle["backlog"])
        self.assertTrue(any("Release Phase" in error for error in errors))

    def test_project_cannot_invent_an_owner_field(self):
        config = load_json(ROOT / "planning" / "project-config.json")
        config["fields"].append({"name": "Owner", "type": "TEXT"})
        errors = validate_project_config(config, self.bundle["backlog"])
        self.assertTrue(any("native Assignees" in error for error in errors))

    def test_schema_rejects_boolean_as_numeric_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "planning", root / "planning")
            shutil.copytree(ROOT / "schemas" / "planning", root / "schemas" / "planning")
            path = root / "planning" / "release-manifest.json"
            manifest = load_json(path)
            manifest["bootstrap"]["production_record_count"] = False
            path.write_text(json.dumps(manifest))
            self.assertTrue(any("production_record_count" in error for error in validate_repository(root)))

    def test_strict_reader_rejects_ambiguous_and_nonfinite_json(self):
        bad_documents = [
            '{"outer": {"id": "first", "id": "second"}}',
            '{"count": NaN}', '{"count": Infinity}', '{"count": -Infinity}', '{"count": 1e9999}',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for raw in bad_documents:
                with self.subTest(raw=raw):
                    path.write_text(raw)
                    with self.assertRaises(ValueError):
                        load_json(path)

    @staticmethod
    def receipt():
        return {
            "reviewer": "fixture-maintainer",
            "scope": "Fictional in-memory receipt for validator tests; no real approval is claimed.",
            "url": "https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/pull/999999",
            "reviewed_commit": "a" * 40,
            "submitted_at": "2026-10-22T12:00:00Z",
            "synthetic": False,
        }


if __name__ == "__main__":
    unittest.main()
