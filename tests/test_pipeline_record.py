"""Offline envelope semantics for fictional records only."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.validate_examples import PIPELINE_EXAMPLE, pipeline_example_errors, read_json


ROOT = Path(__file__).resolve().parents[1]


class PipelineRecordTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "examples" / PIPELINE_EXAMPLE
        self.path.parent.mkdir(parents=True)
        self.records = read_json(ROOT / "examples" / PIPELINE_EXAMPLE)

    def check(self, records=None):
        self.path.write_text(json.dumps(self.records if records is None else records),
                             encoding="utf-8")
        return pipeline_example_errors(self.root)

    def record(self, kind):
        return next(record for record in self.records if record["entity_kind"] == kind)

    def test_fixture_covers_exact_benchmark_chain_and_field_states(self):
        self.assertEqual(self.check(), [])
        suite = self.record("benchmark_suite")
        run = self.record("benchmark_run")
        result = self.record("benchmark_result")
        self.assertEqual(run["relationships"][0]["target_id"], suite["id"])
        self.assertEqual(result["relationships"][0]["target_id"], run["id"])
        self.assertEqual(result["fields"]["benchmark.score"]["value"]["data"], "0.00")
        self.assertIs(self.record("application")["fields"]["app.offline"]["value"]["data"], False)
        self.assertEqual(set(
            field["state"] for record in self.records for field in record["fields"].values()
        ), {"known", "unknown", "unsupported", "not_applicable"})

    def test_other_versions_kinds_and_publication_authority_are_rejected(self):
        for name, value in [
            ("schema_version", "catalog-pipeline-draft-0.1.0"),
            ("schema_version", "1.0.0"),
            ("entity_kind", "foreign_kind"),
            ("synthetic", False),
            ("publication_state", "published"),
            ("provenance", []),
            ("unrecognized_field", "fixture prose"),
        ]:
            with self.subTest(name=name, value=value):
                self.assertTrue(self.check([{**self.records[0], name: value}]))

    def test_field_states_require_explicit_values_or_reasons(self):
        for field in [
            None,
            {"state": "known"},
            {"state": "known", "value": {"type": "integer", "data": False}},
            {"state": "known", "value": {"type": "integer", "data": 1.0}},
            {"state": "known", "value": {"type": "decimal", "data": "1e2"}},
            {"state": "unknown", "reason": "  "},
            {"state": "unsupported", "value": {"type": "integer", "data": 0}},
            {"state": "not_applicable", "reason": "Fixture context", "value": None},
        ]:
            with self.subTest(field=field):
                self.assertTrue(self.check([{**self.records[0], "fields": {"x": field}}]))
        self.assertEqual(self.check([{**self.records[0], "fields": {}}]), [])

    def test_dangling_and_duplicate_revisions_are_rejected(self):
        records = deepcopy(self.records)
        result = next(record for record in records if record["entity_kind"] == "benchmark_result")
        result["relationships"][0]["target_revision"] += 1
        self.assertTrue(any("unlisted target revision" in message for message in self.check(records)))
        self.assertTrue(any("duplicate record revision" in message
                            for message in self.check(self.records + [self.records[0]])))

    def test_extensions_reject_unreserved_namespaces(self):
        valid = self.record("tool")
        self.assertEqual(self.check([valid]), [])
        invalid = {**valid, "extensions": {"unrecognized": valid["fields"]}}
        self.assertTrue(self.check([invalid]))
