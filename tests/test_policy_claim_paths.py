"""Independent offline regression tests for PR #88 per-record claim paths.

This test file was authored without viewing or editing the root implementation.
Only synthetic committed fixtures are used. No API, source fetch, or publication
operation is performed. Lifecycle and URL semantics are outside this change.

Original-head reproduction from the canonical clone::

    POLICY_SOURCE_REVISION=f1802a1b644c76466b93695662b18ec33cc7f40e \
      python -m unittest discover -s tests \
      -p test_policy_claim_paths.py -v

To test a separately prepared implementation, set POLICY_MODULE_PATH to its
scripts/validate_examples.py. The module supplies ROOT for its checked-in schemas
and fixtures; no implementation-private functions are inspected by these tests.

Before-fix evidence (2026-11-18, Python 3.12.14): the original exact source above
returned (True, []) for both duplicate-path negatives. The two positive controls
passed. The four-test run failed with exactly two assertion failures, as intended.
This is local offline behavior, not a production or receiving-acceptance result.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import types
import unittest


FIXED_DUPLICATE_REASON = "Duplicate claim paths within a record are denied."
CALLER_PATH = "untrusted.caller_path_sentinel"
ORIGINAL_REVISION = "f1802a1b644c76466b93695662b18ec33cc7f40e"


def load_policy_module():
    """Select an explicit test target without checking out or changing sources."""
    selected_path = os.environ.get("POLICY_MODULE_PATH")
    if selected_path:
        module_path = Path(selected_path).resolve()
    else:
        # Works in the delivered campaign location and when copied to repo/tests.
        parent = Path(__file__).resolve().parents[1]
        candidate = parent / "scripts" / "validate_examples.py"
        module_path = candidate if candidate.is_file() else (
            parent / "catalog-pipeline" / "scripts" / "validate_examples.py"
        )
    revision = os.environ.get("POLICY_SOURCE_REVISION")
    if revision:
        if selected_path:
            raise RuntimeError("Choose POLICY_MODULE_PATH or POLICY_SOURCE_REVISION, not both")
        if revision != ORIGINAL_REVISION:
            raise RuntimeError("The red-evidence target must be the pinned original PR #88 head")
        repository = module_path.parents[1]
        source = subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{revision}:scripts/validate_examples.py"],
            text=True,
        )
        module = types.ModuleType("independent_claim_path_policy")
        module.__file__ = str(module_path)
        exec(compile(source, f"PR88@{revision}/scripts/validate_examples.py", "exec"), module.__dict__)
        return module
    spec = importlib.util.spec_from_file_location("independent_claim_path_policy", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the explicitly selected policy module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PerRecordClaimPathPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy_module()
        cls.fixture_root = Path(cls.policy.ROOT) / "examples"

    def setUp(self):
        def fixture(name):
            return json.loads((self.fixture_root / name).read_text())

        self.record = fixture("synthetic-model.json")
        self.other_record = fixture("synthetic-hardware.json")
        self.rights = fixture("synthetic-source-rights.json")
        self.product = self.rights["scope"]["product_id"]

    def decide(self, records):
        return self.policy.fixture_policy_decision(
            records, [self.rights], "display", self.product
        )

    def duplicate_first_claim(self, *, conflicting):
        # Keep both claim IDs distinct, so the existing duplicate-ID check cannot
        # satisfy this test. A caller-supplied valid path must not leak into errors.
        self.record["claims"][0]["path"] = CALLER_PATH
        self.rights["scope"]["claim_paths"].append(CALLER_PATH)
        duplicate = deepcopy(self.record["claims"][0])
        duplicate["id"] += ":duplicate-path"
        if conflicting:
            duplicate["value"] += 1
        self.record["claims"].append(duplicate)

    def test_identical_value_duplicate_path_with_distinct_ids_is_denied(self):
        self.duplicate_first_claim(conflicting=False)
        self.assertNotEqual(self.record["claims"][0]["id"], self.record["claims"][-1]["id"])
        self.assertEqual(
            self.decide([self.record]),
            (False, [FIXED_DUPLICATE_REASON]),
        )

    def test_conflicting_value_duplicate_path_with_distinct_ids_is_denied(self):
        self.duplicate_first_claim(conflicting=True)
        self.assertNotEqual(self.record["claims"][0]["value"], self.record["claims"][-1]["value"])
        self.assertEqual(
            self.decide([self.record]),
            (False, [FIXED_DUPLICATE_REASON]),
        )

    def test_distinct_paths_within_one_record_remain_allowed(self):
        paths = [claim["path"] for claim in self.record["claims"]]
        self.assertGreater(len(paths), 1)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(self.decide([self.record]), (True, []))

    def test_same_path_across_distinct_records_remains_allowed(self):
        first_paths = {claim["path"] for claim in self.record["claims"]}
        other_paths = {claim["path"] for claim in self.other_record["claims"]}
        self.assertNotEqual(self.record["id"], self.other_record["id"])
        self.assertIn("evidence.independent_result", first_paths & other_paths)
        self.assertEqual(self.decide([self.record, self.other_record]), (True, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
