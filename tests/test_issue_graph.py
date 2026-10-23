"""Synthetic, offline tests for the repository-scoped native graph initializer."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publish_plan as pub
import reconcile_issue_graph as graph

HELPER_SPEC = importlib.util.spec_from_file_location("graph_test_helpers", ROOT / "tests/test_publish_plan.py")
helpers = importlib.util.module_from_spec(HELPER_SPEC)
HELPER_SPEC.loader.exec_module(helpers)


class GraphRemote(helpers.FakeGitHub):
    """Existing synthetic issues with independently observable graph state."""
    def __init__(self, payload, config):
        super().__init__()
        self.create_repository(config)
        self.repo_value.update(id=graph.REPOSITORY_ID)
        for item in payload["items"]:
            self.create_issue(item)
        for issue in self.issue_rows:
            issue.update(type=None, comments=0, milestone=None, locked=False)
        self.writes.clear()
        self.parent_failure = None
        self.silently_ignore_type = False
        self.before_metadata = None
        self.truncated_labels = False
        self.non_user_actors = 0
        self.rest_requests = 0
        self.graphql_requests = 0

    def issues(self):
        self.rest_requests += 1
        return super().issues()

    def parents(self, issues):
        self.graphql_requests += 1
        return super().parents(issues)

    def blockers(self, number):
        self.rest_requests += 1
        return super().blockers(number)

    def graphql(self, query, variables):
        self.graphql_requests += 1
        if query.lstrip().startswith("mutation"):
            raise AssertionError("GraphQL is read-only in this initializer")
        if "subIssues(first:100)" in query:
            rows = [{"id": row["node_id"]} for row in self.issue_rows
                    if self.parent_rows.get(row["node_id"], {}).get("id") == variables["id"]]
            return {"node": {"id": variables["id"], "subIssues": {"nodes": rows, "totalCount": len(rows),
                                                                   "pageInfo": {"hasNextPage": False}}}}
        if "fullDatabaseId" not in query:
            raise AssertionError("Unknown GraphQL read")
        if self.before_metadata:
            self.before_metadata(self)
        nodes = []
        for node_id in variables["ids"]:
            row = next(row for row in self.issue_rows if row["node_id"] == node_id)
            labels = [{"name": label} if isinstance(label, str) else label for label in row["labels"]]
            nodes.append({"id": row["node_id"], "fullDatabaseId": str(row["id"]), "number": row["number"],
                          "url": row["html_url"], "title": row["title"], "body": row["body"],
                          "state": row["state"].upper(), "locked": row["locked"],
                          "repository": {"nameWithOwner": pub.REPO}, "issueType": row["type"],
                          "milestone": row["milestone"], "comments": {"totalCount": row["comments"]},
                          "assignedActors": {"totalCount": len(row["assignees"]) + self.non_user_actors},
                          "labels": {"nodes": labels, "totalCount": len(labels),
                                     "pageInfo": {"hasNextPage": self.truncated_labels}}})
        return {"nodes": deepcopy(nodes)}

    def rest(self, endpoint, method="GET", data=None, paginate=False):
        self.rest_requests += 1
        if endpoint == f"repos/{pub.REPO}" and method == "GET":
            return deepcopy(self.repo_value)
        if method == "PATCH" and endpoint.startswith(f"repos/{pub.REPO}/issues/"):
            self.assert_type_only(data)
            number = int(endpoint.rsplit("/", 1)[1])
            self.writes.append(f"type:{number}:{data['type']}")
            if not self.silently_ignore_type:
                row = next(row for row in self.issue_rows if row["number"] == number)
                row["type"] = {"name": data["type"]}
            return self.issue(number)
        raise AssertionError(f"Unpermitted fake request: {method} {endpoint}")

    @staticmethod
    def assert_type_only(data):
        if set(data) != {"type"} or data["type"] not in {"Feature", "Task"}:
            raise AssertionError("Initializer attempted to edit other issue fields")

    def add_parent(self, parent, child):
        self.rest_requests += 1
        failure, self.parent_failure = self.parent_failure, None
        if failure == "before":
            raise pub.RemoteError("Synthetic uncertain request")
        super().add_parent(parent, child)
        if failure == "after":
            raise pub.RemoteError("Synthetic lost response after successful write")

    def add_blocker(self, issue, blocker):
        self.rest_requests += 1
        super().add_blocker(issue, blocker)


class IssueGraphTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.payload, self.config = helpers.fixture()
        self.api = GraphRemote(self.payload, self.config)
        self.path = Path(self.temp.name) / "journal.json"
        self.fingerprint = pub.digest({"payload": self.payload, "config": self.config})
        self.journal = pub.Journal(self.path, self.fingerprint)

    def initializer(self):
        return graph.GraphInitializer(self.api, self.payload, self.config, self.journal)

    def test_applies_only_native_metadata_with_exact_inverse_readback(self):
        report = self.initializer().apply()
        self.assertEqual(report["observed_counts"], {"issues": 4, "parent_edges": 3,
                                                    "blocker_edges": 1, "typed_issues": 4})
        self.assertEqual(len(self.api.writes), 8)
        self.assertTrue(report["graph_complete"])
        self.assertFalse(report["complete_mission"])
        self.assertEqual(report["external_parent"]["url"], graph.EXTERNAL_PARENT)

    def test_successful_rerun_preserves_human_progress_without_writes(self):
        self.initializer().apply()
        live = self.api.issue_rows[2]
        live.update(state="closed", assignees=[{"login": "actual-owner"}], comments=3,
                    body=live["body"].replace("[ ]", "[x]"))
        before = deepcopy(live)
        self.api.writes.clear()
        self.assertTrue(self.initializer().apply()["graph_complete"])
        self.assertEqual(self.api.writes, [])
        self.assertEqual(live, before)

    def test_inspect_is_read_only_and_reports_every_missing_edge(self):
        report = self.initializer().inspect()
        self.assertEqual(len(report["missing_parents"]), 3)
        self.assertEqual(report["missing_blockers"], [["CP-01.02", "CP-01.01"]])
        self.assertEqual(len(report["missing_types"]), 4)
        self.assertEqual(self.api.writes, [])

    def test_incomplete_issue_inventory_stops_before_any_mutation(self):
        self.api.issue_rows.pop()
        with self.assertRaisesRegex(pub.PublicationError, "All canonical issues"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_duplicate_marker_stops_before_any_mutation(self):
        duplicate = deepcopy(self.api.issue_rows[0])
        duplicate.update(id=2000, number=99, node_id="I_duplicate")
        self.api.issue_rows.append(duplicate)
        with self.assertRaisesRegex(pub.PublicationError, "duplicate existing plan marker"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_conflicting_parent_and_extra_blocker_are_not_removed(self):
        self.api.parent_rows["I_3"] = {"id": "I_other", "url": "https://github.com/example/other/issues/1"}
        before = deepcopy(self.api.parent_rows)
        with self.assertRaisesRegex(pub.PublicationError, "Conflicting native parent"):
            self.initializer().apply()
        self.assertEqual(self.api.parent_rows, before)
        self.assertEqual(self.api.writes, [])
        self.api.parent_rows.clear()
        self.api.blocker_rows[4] = [self.api.issue_rows[0]]
        with self.assertRaisesRegex(pub.PublicationError, "Unexpected native blockers"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_unplanned_child_is_preserved_and_blocks_application(self):
        outside = deepcopy(self.api.issue_rows[0])
        outside.update(id=12345, number=99, node_id="I_outside", body="Unrelated human issue", title="Unrelated")
        self.api.issue_rows.append(outside)
        self.api.parent_rows["I_outside"] = {"id": "I_1"}
        with self.assertRaisesRegex(pub.PublicationError, "Unexpected native children"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_progressed_untyped_issue_and_conflicting_type_fail_preflight(self):
        self.api.issue_rows[2]["comments"] = 1
        with self.assertRaisesRegex(pub.PublicationError, "has progressed"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])
        self.api.issue_rows[2].update(comments=0, type={"name": "Human-selected type"})
        with self.assertRaisesRegex(pub.PublicationError, "Conflicting native type"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_silent_type_drop_is_not_reported_as_success(self):
        self.api.silently_ignore_type = True
        with self.assertRaisesRegex(pub.PublicationError, "no confirmed readback"):
            self.initializer().apply()
        self.assertEqual(self.journal.data["operations"]["type:CP"]["state"], "intent")
        self.assertEqual(len([w for w in self.api.writes if w.startswith("type:")]), 1)

    def test_concurrent_progress_and_partial_graphql_stop_before_write(self):
        self.api.before_metadata = lambda api: api.issue_rows[1].update(comments=1)
        with self.assertRaisesRegex(pub.PublicationError, "has progressed"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])
        self.api.before_metadata = None
        self.api.issue_rows[1]["comments"] = 0
        self.api.truncated_labels = True
        with self.assertRaisesRegex(pub.PublicationError, "Incomplete or duplicate"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])
        self.api.truncated_labels = False
        self.api.non_user_actors = 1
        with self.assertRaisesRegex(pub.PublicationError, "has progressed"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_full_plan_inspect_and_apply_fit_both_token_budgets(self):
        payload = pub.load_json(ROOT / "planning/github-issue-payloads.json")
        config = pub.load_json(ROOT / "planning/project-config.json")
        api = GraphRemote(payload, config)
        journal = pub.Journal(Path(self.temp.name) / "full.json", pub.digest({"payload": payload, "config": config}))
        initializer = graph.GraphInitializer(api, payload, config, journal)
        initializer.inspect()
        report = initializer.apply()
        self.assertTrue(report["graph_complete"])
        self.assertEqual(len(api.writes), 296)
        # Include one extra main-head REST read in the workflow entry point. Leave
        # margin within each 1,000/hour bucket for checkout and unrelated reads.
        self.assertLessEqual(api.rest_requests + 1, 850)
        self.assertLessEqual(api.graphql_requests, 850)

    def test_lost_successful_response_recovers_by_identity_without_duplicate(self):
        self.api.parent_failure = "after"
        with self.assertRaises(pub.RemoteError):
            self.initializer().apply()
        self.assertEqual(self.journal.data["operations"]["parent:CP-01"]["state"], "intent")
        self.initializer().apply()
        self.assertEqual(self.api.writes.count("parent:2"), 1)
        self.assertTrue(self.journal.data["operations"]["parent:CP-01"]["recovered_after_uncertain_write"])

    def test_absent_uncertain_write_is_never_retried_with_its_receipt(self):
        self.api.parent_failure = "before"
        with self.assertRaises(pub.RemoteError):
            self.initializer().apply()
        with self.assertRaisesRegex(pub.PublicationError, "Uncertain or disappeared"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_external_research_parent_is_read_only_and_never_targeted(self):
        self.api.parent_rows["I_1"] = {"id": "I_external", "url": graph.EXTERNAL_PARENT,
                                        "number": 509, "repository": {"nameWithOwner": "Pick-Your-AI/pick-your-ai-research"}}
        self.initializer().apply()
        self.assertEqual(self.api.parent_rows["I_1"]["url"], graph.EXTERNAL_PARENT)
        self.assertFalse(any("509" in write for write in self.api.writes))

    def test_repository_identity_and_issue_url_are_checked(self):
        self.api.repo_value["id"] = 42
        with self.assertRaisesRegex(pub.PublicationError, "Repository identity"):
            self.initializer().apply()
        self.api.repo_value["id"] = graph.REPOSITORY_ID
        self.api.issue_rows[0]["html_url"] = "https://github.com/foreign/repo/issues/1"
        with self.assertRaisesRegex(pub.PublicationError, "Issue URL"):
            self.initializer().apply()
        self.assertEqual(self.api.writes, [])

    def test_resume_receipt_preserves_intent_and_rejects_scope_expansion(self):
        self.journal.data["operations"]["type:CP"] = {"state": "intent", "created_by_helper": False}
        graph.restore_journal(self.path, json.dumps(self.journal.data), self.fingerprint, self.payload["items"])
        restored = pub.Journal(self.path, self.fingerprint)
        self.assertEqual(restored.data["operations"]["type:CP"]["state"], "intent")
        value = deepcopy(self.journal.data)
        value["operations"]["repository"] = {"state": "intent"}
        with self.assertRaisesRegex(pub.PublicationError, "does not match"):
            graph.restore_journal(self.path, json.dumps(value), self.fingerprint, self.payload["items"])
        duplicate = json.dumps(self.journal.data).replace('"operations":', '"operations": {}, "operations":')
        with self.assertRaisesRegex(pub.PublicationError, "duplicate JSON"):
            graph.restore_journal(self.path, duplicate, self.fingerprint, self.payload["items"])

    def test_apply_context_rejects_fork_branch_unapproved_actor_and_rerun(self):
        valid = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": pub.REPO,
                 "GITHUB_REPOSITORY_ID": str(graph.REPOSITORY_ID), "GITHUB_REF": "refs/heads/main",
                 "GITHUB_ACTOR": "CompleteDotTech", "GITHUB_TRIGGERING_ACTOR": "CompleteDotTech",
                 "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40}
        graph.authorize_actions(valid)
        for key, value in [("GITHUB_REPOSITORY", "foreign/repo"), ("GITHUB_REF", "refs/heads/contrib/x/y"),
                           ("GITHUB_TRIGGERING_ACTOR", "unapproved"), ("GITHUB_RUN_ATTEMPT", "2"),
                           ("GITHUB_EVENT_NAME", "pull_request")]:
            with self.subTest(key=key), self.assertRaises(pub.PublicationError):
                graph.authorize_actions({**valid, key: value})

    def test_offline_default_and_bad_hash_never_instantiate_network(self):
        with patch.object(graph, "GitHub") as transport, patch.dict("os.environ", {}, clear=True), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(graph.main([]), 0)
            report = json.loads(output.getvalue())
            self.assertFalse(report["network_used"])
            self.assertEqual(report["planned_counts"], {"issues": 81, "parent_edges": 80, "blocker_edges": 135})
            transport.assert_not_called()
        with patch.object(graph, "GitHub") as transport, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(graph.main(["--apply", "--expected-plan-sha256", "0" * 64]), 2)
            transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
