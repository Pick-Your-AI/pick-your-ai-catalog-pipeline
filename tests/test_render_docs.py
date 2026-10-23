"""Meaningful checks for immutable planning projections and publication payloads."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("catalog_render_docs", ROOT / "scripts/render_docs.py")
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class RenderDocsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "planning").mkdir()
        for relative in renderer.SOURCES.values():
            shutil.copyfile(ROOT / relative, self.root / relative)

    def run_renderer(self, *arguments):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = renderer.main(["--root", str(self.root), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_check_reports_missing_outputs_without_writing(self):
        code, _, error = self.run_renderer("--check")
        self.assertEqual(code, 1)
        self.assertIn("Missing generated output: docs/DELIVERY_PLAN.md", error)
        self.assertFalse((self.root / "planning/issues").exists())

    def test_render_is_deterministic_and_preserves_source_and_unrelated_files(self):
        sources = {relative: (self.root / relative).read_bytes() for relative in renderer.SOURCES.values()}
        unrelated = self.root / "docs/HUMAN-NOTES.md"
        unrelated.parent.mkdir()
        unrelated.write_text("Keep this independently authored note.\n")
        self.assertEqual(self.run_renderer()[0], 0)
        first = {relative: (self.root / relative).read_bytes() for relative in renderer.expected_outputs(self.root)}
        self.assertEqual(self.run_renderer()[0], 0)
        second = {relative: (self.root / relative).read_bytes() for relative in first}
        self.assertEqual(first, second)
        self.assertEqual(sources, {relative: (self.root / relative).read_bytes() for relative in sources})
        self.assertEqual(unrelated.read_text(), "Keep this independently authored note.\n")
        self.assertEqual(self.run_renderer("--check")[0], 0)

    def test_check_detects_drift_and_missing_file_without_repair(self):
        self.assertEqual(self.run_renderer()[0], 0)
        altered = self.root / "planning/issues/CP-03.01.md"
        altered.write_text(altered.read_text() + "Unreviewed changed condition.\n")
        missing = self.root / "docs/DEPENDENCIES.md"
        missing.unlink()
        code, _, error = self.run_renderer("--check")
        self.assertEqual(code, 1)
        self.assertIn("Generated output drift: planning/issues/CP-03.01.md", error)
        self.assertIn("Missing generated output: docs/DEPENDENCIES.md", error)
        self.assertTrue(altered.read_text().endswith("Unreviewed changed condition.\n"))
        self.assertFalse(missing.exists())

    def test_payload_preserves_all_symbolic_relationships_and_unique_markers(self):
        bundle, _ = renderer.load_sources(self.root)
        records = renderer.native_records(bundle["backlog"])
        output = renderer.expected_outputs(self.root)
        payload = json.loads(output["planning/github-issue-payloads.json"])
        items = payload["items"]
        self.assertEqual(len(items), len(records))
        self.assertEqual(len({item["id"] for item in items}), len(records))
        by_id = {item["id"]: item for item in items}
        for record in records:
            item = by_id[record["id"]]
            self.assertEqual(item["parent_id"], record.get("parent"))
            self.assertEqual(item["blocked_by"], record.get("blocked_by", []))
            self.assertEqual(item["body"].count(renderer.marker(item["id"])), 1)
            self.assertEqual(item["body"], output[f"planning/issues/{item['id']}.md"])
            self.assertEqual(item["assignees"], [])
            self.assertNotIn("issue_number", item)
            self.assertNotIn("project_id", item)
        self.assertEqual(payload["mutation_policy"], "create_missing_preserve_live")
        self.assertFalse(payload["reset_existing_progress"])

    def test_checklist_is_task_progress_not_duplicate_child_progress(self):
        bundle, _ = renderer.load_sources(self.root)
        records = renderer.native_records(bundle["backlog"])
        for record in records:
            body = renderer.issue_body(record, records)
            checkboxes = body.count("- [ ]") + body.count("- [x]")
            if record["level"] in ("Program", "Epic"):
                self.assertEqual(checkboxes, 0)
            else:
                expected = sum(1 + len(task["subtasks"]) for task in record["tasks"])
                self.assertEqual(checkboxes, expected)
        changed = records[2]["tasks"][0]
        changed["done"] = True
        self.assertIn(f"- [x] `{changed['id']}`", renderer.issue_body(records[2], records))

    def test_source_changes_invalidate_payload_even_without_visible_text_changes(self):
        self.assertEqual(self.run_renderer()[0], 0)
        source = self.root / "planning/decision-register.json"
        source.write_bytes(source.read_bytes() + b"\n")
        code, _, error = self.run_renderer("--check")
        self.assertEqual(code, 1)
        self.assertIn("Generated output drift: planning/github-issue-payloads.json", error)

    def test_unknown_issue_file_is_preserved_and_blocks_silent_scope_removal(self):
        self.assertEqual(self.run_renderer()[0], 0)
        stale = self.root / "planning/issues/CP-99.md"
        stale.write_text("Retained unique scope requiring reconciliation.\n")
        code, _, error = self.run_renderer()
        self.assertEqual(code, 1)
        self.assertIn("Unexpected generated issue file", error)
        self.assertEqual(stale.read_text(), "Retained unique scope requiring reconciliation.\n")

    def test_unsafe_native_id_and_duplicate_json_are_rejected(self):
        source = self.root / "planning/project-backlog.json"
        data = json.loads(source.read_text())
        data["epics"][0]["id"] = "../../outside"
        source.write_text(json.dumps(data))
        code, _, error = self.run_renderer()
        self.assertEqual(code, 1)
        self.assertIn("unsafe or unsupported native record ID", error)
        source.write_text('{"program": {}, "program": {}}')
        code, _, error = self.run_renderer()
        self.assertEqual(code, 1)
        self.assertIn("duplicate JSON key", error)


if __name__ == "__main__":
    unittest.main()
