"""Offline safety and reconciliation tests. No test invokes gh or the network."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publish_plan.py"
SPEC = importlib.util.spec_from_file_location("catalog_publisher", SCRIPT)
pub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pub)


def fixture():
    config = {"owner": pub.OWNER, "repository": pub.REPO, "title": pub.TITLE,
              "description": "Synthetic offline publisher test", "public": True,
              "fields": [
                  {"name": "Status", "type": "SINGLE_SELECT", "native": True,
                   "options": ["Backlog", "Ready", "In Progress", "In Review", "Blocked", "Done"]},
                  {"name": "Record Type", "type": "SINGLE_SELECT", "native": False,
                   "options": ["Program", "Epic", "Work Package", "Task"]}],
              "labels": [{"name": "contracts", "color": "123456", "description": "Test label"}]}
    items = []
    for key, parent, record_type in [("CP", None, "Program"), ("CP-01", "CP", "Epic"),
                                     ("CP-01.01", "CP-01", "Work Package"),
                                     ("CP-01.02", "CP-01", "Work Package")]:
        items.append({"id": key, "parent_id": parent, "title": f"[Synthetic] {key}",
                      "body": f"Synthetic fixture only.\n<!-- pick-your-ai-catalog-pipeline:{key} -->\n- [ ] Review",
                      "issue_type": "Task" if parent == "CP-01" else "Feature", "assignees": [], "labels": [],
                      "blocked_by": ["CP-01.01"] if key == "CP-01.02" else [],
                      "project_fields": {"Status": "Backlog", "Record Type": record_type}})
    return {"repository": pub.REPO, "items": items}, config


class FakeGitHub:
    """A stateful remote model; every write is recorded and all reads are copies."""
    def __init__(self):
        self.repo_value = None
        self.project_value = None
        self.field_rows = []
        self.issue_rows = []
        self.parent_rows = {}
        self.blocker_rows = {}
        self.members = {}
        self.labels = []
        self.writes = []
        self.after_value = None

    def repo(self):
        return deepcopy(self.repo_value)

    def project(self):
        return deepcopy(self.project_value)

    def fields(self, project):
        return deepcopy(self.field_rows)

    def issues(self):
        return deepcopy(self.issue_rows)

    def issue(self, number):
        return deepcopy(next(row for row in self.issue_rows if row["number"] == number))

    def parents(self, issues):
        return {row["node_id"]: deepcopy(self.parent_rows.get(row["node_id"])) for row in issues}

    def blockers(self, number):
        return deepcopy(self.blocker_rows.get(number, []))

    def project_items(self, project):
        return deepcopy(list(self.members.values()))

    def create_repository(self, config):
        self.writes.append("repository")
        self.repo_value = {"id": 100, "node_id": "R_target", "identity": 100,
                           "full_name": pub.REPO, "default_branch": "main", "private": False}

    def create_project(self):
        self.writes.append("project")
        self.project_value = {"id": "PVT_discovered", "identity": "PVT_discovered", "number": 42,
                              "title": pub.TITLE, "public": False, "closed": False,
                              "viewerCanUpdate": True, "repositories": [], "shortDescription": "",
                              "url": "https://github.com/orgs/Pick-Your-AI/projects/42"}
        self.field_rows = [{"id": "F_status", "name": "Status", "dataType": "SINGLE_SELECT",
                            "options": [{"id": f"O_status_{i}", "name": name} for i, name in
                                        enumerate(["Todo", "In Progress", "Done"])]}]

    def initialize_project(self, project, config):
        self.writes.append("project-metadata")
        self.project_value.update(public=True, shortDescription=config["description"])

    def link_project(self, project, repo):
        self.writes.append("project-link")
        self.project_value["repositories"].append(pub.REPO)

    def initialize_status(self, field, options):
        self.writes.append("status-options")
        actual = next(row for row in self.field_rows if row["id"] == field["id"])
        actual["options"] = [{"id": f"O_status_final_{i}", "name": name} for i, name in enumerate(options)]

    def create_field(self, project, field):
        self.writes.append(f"field:{field['name']}")
        fid = f"F_{len(self.field_rows)}"
        self.field_rows.append({"id": fid, "name": field["name"], "dataType": "SINGLE_SELECT",
                                "options": [{"id": f"{fid}_{i}", "name": name} for i, name in enumerate(field["options"])]})

    def create_issue(self, item):
        self.writes.append(f"issue:{item['id']}")
        number = len(self.issue_rows) + 1
        row = {"id": 1000 + number, "node_id": f"I_{number}", "number": number,
               "repository_url": f"https://api.github.com/repos/{pub.REPO}",
               "html_url": f"https://github.com/{pub.REPO}/issues/{number}",
               "title": item["title"], "body": item["body"], "state": "open", "assignees": [],
               "labels": deepcopy(item["labels"]), "type": {"name": item["issue_type"]}}
        self.issue_rows.append(row)
        return deepcopy(row)

    def add_parent(self, parent, child):
        self.writes.append(f"parent:{child['number']}")
        if self.parent_rows.get(child["node_id"]):
            raise AssertionError("Replacing a parent is forbidden")
        self.parent_rows[child["node_id"]] = {"id": parent["node_id"], "url": parent["html_url"],
                                             "number": parent["number"], "repository": {"nameWithOwner": pub.REPO}}

    def add_blocker(self, issue, blocker):
        self.writes.append(f"blocker:{issue['number']}:{blocker['number']}")
        self.blocker_rows.setdefault(issue["number"], []).append(deepcopy(blocker))

    def add_item(self, project, issue):
        self.writes.append(f"item:{issue['number']}")
        self.members[issue["node_id"]] = {"id": f"PVTI_{issue['number']}", "identity": f"PVTI_{issue['number']}",
                                         "isArchived": False, "values": {},
                                         "content": {"__typename": "Issue", "id": issue["node_id"],
                                                     "number": issue["number"], "url": issue["html_url"],
                                                     "repository": {"nameWithOwner": pub.REPO}}}

    def set_value(self, project, item, field, option):
        self.writes.append(f"value:{item['id']}:{field['name']}:{option['name']}")
        actual = next(row for row in self.members.values() if row["id"] == item["id"])
        actual["values"][field["name"]] = option["name"]
        if self.after_value:
            self.after_value(actual, field)

    def rest(self, endpoint, method="GET", data=None, paginate=False):
        if endpoint == f"repos/{pub.REPO}/labels?per_page=100" and method == "GET":
            return deepcopy(self.labels)
        if endpoint == f"repos/{pub.REPO}/labels" and method == "POST":
            self.writes.append(f"label:{data['name']}")
            self.labels.append({"id": len(self.labels) + 1, **deepcopy(data)})
            return deepcopy(self.labels[-1])
        raise AssertionError(f"Unexpected fake REST request: {method} {endpoint}")


class PublisherTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.payload, self.config = fixture()
        self.api = FakeGitHub()
        self.journal = pub.Journal(Path(self.directory.name) / "journal.json",
                                   pub.digest({"payload": self.payload, "config": self.config}))

    def apply(self):
        return pub.Publisher(self.api, self.payload, self.config, self.journal).apply()

    def test_new_setup_creates_native_edges_and_discovers_actual_project(self):
        report = self.apply()
        self.assertEqual(report["counts"], {"issues": 4, "project_items": 4, "parent_edges": 3, "blocker_edges": 1})
        self.assertEqual(report["project"]["number"], 42)
        self.assertEqual(report["field_differences"], [])
        self.assertFalse(report["complete_mission"])
        self.assertIn("status-options", self.api.writes)
        self.assertEqual(len(self.api.parent_rows), 3)
        self.assertEqual(self.api.blocker_rows[4][0]["id"], self.api.issue_rows[2]["id"])
        self.assertTrue((Path(self.directory.name) / "readback.json").exists())

    def test_rerun_has_no_writes_and_preserves_closed_owned_issue_and_fields(self):
        self.apply()
        self.api.writes.clear()
        issue = self.api.issue_rows[2]
        issue.update(state="closed", assignees=[{"login": "human"}])
        issue["body"] = issue["body"].replace("[ ]", "[x]")
        self.api.members[issue["node_id"]]["values"]["Status"] = "Done"
        before = deepcopy(issue)
        report = self.apply()
        self.assertEqual(self.api.writes, [])
        self.assertEqual(issue, before)
        self.assertEqual(self.api.members[issue["node_id"]]["values"]["Status"], "Done")
        self.assertTrue(any(d["id"] == "CP-01.01" and d["observed"] == "Done" for d in report["field_differences"]))
        drift = next(row for row in report["issue_differences"] if row["id"] == "CP-01.01")
        self.assertEqual(set(drift["fields"]), {"body", "state", "assignees"})
        self.assertNotEqual(drift["baseline_content_sha256"], drift["observed_content_sha256"])

    def test_preexisting_closed_issue_newly_added_gets_no_baseline_fields(self):
        self.api.create_repository(self.config)
        self.api.create_issue(self.payload["items"][2])
        existing = self.api.issue_rows[0]
        existing.update(state="closed", assignees=[{"login": "human"}])
        existing["body"] = existing["body"].replace("[ ]", "[x]")
        before = deepcopy(existing)
        report = self.apply()
        self.assertEqual(existing, before)
        self.assertEqual(self.api.members[existing["node_id"]]["values"], {})
        self.assertIn("CP-01.01", report["preserved_existing"])

    def test_resume_created_issue_that_progressed_before_membership_is_preserved(self):
        self.api.create_repository(self.config)
        planned = self.payload["items"][2]
        def observe():
            row = pub.issue_index(self.payload["items"], self.api.issues()).get(planned["id"])
            return {**row, "identity": row["id"]} if row else None
        self.journal.ensure("issue:CP-01.01", observe, lambda: self.api.create_issue(planned))
        self.api.issue_rows[0]["state"] = "closed"
        self.apply()
        self.assertTrue(self.journal.owns("issue:CP-01.01"))
        self.assertEqual(self.api.members[self.api.issue_rows[0]["node_id"]]["values"], {})

    def test_issue_progress_during_fields_stops_before_later_initialization(self):
        def close_after_first_field(member, field):
            row = next(issue for issue in self.api.issue_rows if issue["node_id"] == member["content"]["id"])
            row["state"] = "closed"
        self.api.after_value = close_after_first_field
        with self.assertRaisesRegex(pub.PublicationError, "progressed"):
            self.apply()
        values = [write for write in self.api.writes if write.startswith("value:")]
        self.assertEqual(len(values), 1)
        self.assertNotIn("Record Type", self.api.members["I_1"]["values"])

    def test_existing_project_status_options_are_not_rewritten(self):
        self.api.create_project()
        self.api.project_value["public"] = True
        before = deepcopy(self.api.field_rows)
        self.api.writes.clear()
        with self.assertRaisesRegex(pub.PublicationError, "manual configuration"):
            self.apply()
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.api.field_rows, before)

    def test_existing_private_project_stops_before_repository_creation(self):
        self.api.create_project()
        self.api.writes.clear()
        with self.assertRaisesRegex(pub.PublicationError, "private"):
            self.apply()
        self.assertEqual(self.api.writes, [])
        self.assertIsNone(self.api.repo_value)

    def test_reused_project_metadata_and_issue_scope_drift_are_reported(self):
        self.apply()
        self.api.project_value["shortDescription"] = "A maintained live description"
        issue = self.api.issue_rows[2]
        issue["title"] = "A reviewed replacement title"
        issue["type"] = {"name": "Feature"}
        issue["labels"] = [{"name": "reviewed"}]
        # A different checkout has no ownership receipts for these existing resources.
        adopted = pub.Journal(Path(self.directory.name) / "adopted/journal.json", self.journal.data["fingerprint"])
        self.api.writes.clear()
        report = pub.Publisher(self.api, self.payload, self.config, adopted).apply()
        self.assertEqual(self.api.writes, [])
        difference = next(row for row in report["project_differences"] if row["field"] == "description")
        self.assertEqual(difference["observed"], "A maintained live description")
        drift = next(row for row in report["issue_differences"] if row["id"] == "CP-01.01")
        self.assertEqual(set(drift["fields"]), {"title", "issue_type", "labels"})

    def test_conflicting_parent_fails_before_any_mutation(self):
        self.api.create_repository(self.config)
        for item in self.payload["items"]:
            self.api.create_issue(item)
        self.api.parent_rows["I_3"] = {"id": "I_other", "url": "https://github.com/other/repo/issues/9"}
        self.api.writes.clear()
        with self.assertRaisesRegex(pub.PublicationError, "Conflicting native parent"):
            self.apply()
        self.assertEqual(self.api.writes, [])

    def test_unplanned_blocker_fails_before_any_mutation(self):
        self.api.create_repository(self.config)
        for item in self.payload["items"]:
            self.api.create_issue(item)
        self.api.blocker_rows[3] = [{"id": 999999}]
        self.api.writes.clear()
        with self.assertRaisesRegex(pub.PublicationError, "Unexpected native blockers"):
            self.apply()
        self.assertEqual(self.api.writes, [])


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "journal.json"
        self.journal = pub.Journal(self.path, "test-fingerprint")

    def test_ambiguous_write_is_never_retried_when_readback_absent(self):
        mutation = Mock(side_effect=pub.RemoteError("timeout"))
        with self.assertRaises(pub.RemoteError):
            self.journal.ensure("issue:CP", lambda: None, mutation)
        resumed = pub.Journal(self.path, "test-fingerprint")
        with self.assertRaisesRegex(pub.PublicationError, "Uncertain"):
            resumed.ensure("issue:CP", lambda: None, mutation)
        self.assertEqual(mutation.call_count, 1)

    def test_ambiguous_success_is_reconciled_without_claiming_ownership(self):
        remote = {}
        def mutation():
            remote["issue"] = {"identity": 77}
            raise pub.RemoteError("lost acknowledgement")
        with self.assertRaises(pub.RemoteError):
            self.journal.ensure("issue:CP", lambda: remote.get("issue"), mutation)
        forbidden = Mock(side_effect=AssertionError("duplicate creation"))
        value, created = pub.Journal(self.path, "test-fingerprint").ensure("issue:CP", lambda: remote["issue"], forbidden)
        self.assertEqual(value["identity"], 77)
        self.assertFalse(created)
        forbidden.assert_not_called()

    def test_definite_rejection_can_be_retried(self):
        with self.assertRaises(pub.RemoteError):
            self.journal.ensure("issue:CP", lambda: None, Mock(side_effect=pub.RemoteError("forbidden", 403)))
        remote = {}
        def mutation():
            remote["value"] = {"identity": 99}
        value, created = self.journal.ensure("issue:CP", lambda: remote.get("value"), mutation)
        self.assertTrue(created)
        self.assertEqual(value["identity"], 99)

    def test_verified_identity_change_and_changed_baseline_are_blocked(self):
        remote = {}
        self.journal.ensure("project", lambda: remote.get("value"), lambda: remote.update(value={"identity": "A"}))
        with self.assertRaisesRegex(pub.PublicationError, "identity changed"):
            self.journal.ensure("project", lambda: {"identity": "B"}, Mock())
        with self.assertRaisesRegex(pub.PublicationError, "changed baseline"):
            pub.Journal(self.path, "different-fingerprint")

    def test_publication_lock_cannot_be_stolen(self):
        directory = Path(self.directory.name)
        with pub.publication_lock(directory):
            with self.assertRaisesRegex(pub.PublicationError, "lock exists"):
                with pub.publication_lock(directory):
                    self.fail("second publisher entered")
            self.assertTrue((directory / "publisher.lock").exists())
        self.assertFalse((directory / "publisher.lock").exists())


class InputAndInventoryTest(unittest.TestCase):
    def test_actual_prepared_payload_is_valid_and_dry_run_has_no_subprocess(self):
        root = SCRIPT.parents[1]
        payload = pub.load_json(root / "planning/github-issue-payloads.json")
        config = pub.load_json(root / "planning/project-config.json")
        self.assertEqual(len(pub.validate_inputs(payload, config)), 81)
        with patch.object(pub, "GitHub", side_effect=AssertionError("dry-run constructed a network adapter")), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(pub.main([]), 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result["network_used"])
        self.assertEqual(result["parent_edges"], 80)
        self.assertEqual(result["blocker_edges"], 135)

    def test_wrong_scope_assignment_missing_field_and_dependency_cycle_fail(self):
        for change in (lambda p, c: p.update(repository="other/repo"),
                       lambda p, c: p["items"][0].update(assignees=["invented"]),
                       lambda p, c: p["items"][0]["project_fields"].pop("Status"),
                       lambda p, c: p["items"][2].update(blocked_by=["CP-01.02"])):
            payload, config = fixture()
            change(payload, config)
            with self.subTest(change=change), self.assertRaises(pub.PublicationError):
                pub.validate_inputs(payload, config)

    def test_parent_dependency_and_later_phase_prerequisite_are_rejected(self):
        payload, config = fixture()
        payload["items"][2]["blocked_by"] = ["CP-01"]
        with self.assertRaisesRegex(pub.PublicationError, "Ancestor dependency"):
            pub.validate_inputs(payload, config)
        payload, config = fixture()
        config["fields"].append({"name": "Release Phase", "type": "SINGLE_SELECT", "options": ["Foundation", "Beta"]})
        for item in payload["items"]:
            item["project_fields"]["Release Phase"] = "Foundation"
        payload["items"][2]["project_fields"]["Release Phase"] = "Beta"
        with self.assertRaisesRegex(pub.PublicationError, "Later-phase prerequisite"):
            pub.validate_inputs(payload, config)

    def test_duplicate_marker_matching_unmarked_title_and_foreign_repository_fail(self):
        payload, _ = fixture()
        api = FakeGitHub()
        api.create_issue(payload["items"][0])
        original = api.issues()[0]
        duplicate = {**original, "id": 9999, "node_id": "I_9999", "number": 9999}
        unmarked = {**original, "body": "An existing manually created issue"}
        foreign = {**original, "repository_url": "https://api.github.com/repos/other/repo"}
        for rows in ([original, duplicate], [unmarked], [foreign]):
            with self.subTest(rows=rows), self.assertRaises(pub.PublicationError):
                pub.issue_index(payload["items"], rows)

    def test_equivalent_and_duplicate_projects_require_reconciliation(self):
        exact = {"id": "P1", "title": pub.TITLE, "repositories": [], "closed": False}
        equivalent = {"id": "P2", "title": "Pick Your AI - Catalog Pipeline", "repositories": [], "closed": False}
        linked = {"id": "P3", "title": "Existing ingestion program", "repositories": [pub.REPO], "closed": False}
        for rows in ([equivalent], [exact, equivalent], [linked], [{**exact, "closed": True}]):
            with self.subTest(rows=rows), self.assertRaises(pub.PublicationError):
                pub.choose_project(rows)


class AdapterTest(unittest.TestCase):
    def test_mutation_uses_safe_argv_and_json_stdin_without_shell(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"id":1}', ""))
        api = pub.GitHub(writable=True, delay=0, runner=runner)
        payload = {"body": "literal $(do-not-run) `do-not-run`\nnew line", "title": "safe"}
        api.rest(f"repos/{pub.REPO}/issues", "POST", payload)
        args, kwargs = runner.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][0], "gh")
        self.assertEqual(json.loads(kwargs["input"]), payload)
        self.assertNotIn("shell", kwargs)
        self.assertNotIn(payload["body"], args[0])
        self.assertEqual(kwargs["env"]["GH_PROMPT_DISABLED"], "1")

    def test_readonly_and_out_of_scope_paths_never_invoke_runner(self):
        runner = Mock()
        api = pub.GitHub(runner=runner)
        with self.assertRaises(pub.PublicationError):
            api.rest(f"repos/{pub.REPO}/issues", "POST", {})
        for endpoint in (f"repos/{pub.REPO}-other/issues", f"repos/{pub.REPO}/../other/issues",
                         f"repos/{pub.REPO}/%2e%2e/other", f"user/memberships/orgs/{pub.OWNER}-other"):
            with self.subTest(endpoint=endpoint), self.assertRaises(pub.PublicationError):
                api.rest(endpoint)
        runner.assert_not_called()

    def test_raw_cli_error_and_credentials_are_not_exposed(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, "sensitive output", "secret-token HTTP 403"))
        api = pub.GitHub(runner=runner)
        with self.assertRaises(pub.RemoteError) as error:
            api.repo()
        self.assertEqual(error.exception.status, 403)
        self.assertNotIn("secret", str(error.exception))
        self.assertNotIn("sensitive", str(error.exception))

    def test_graphql_partial_data_is_rejected(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({"data": {}, "errors": [{"message": "denied"}]}), ""))
        with self.assertRaisesRegex(pub.RemoteError, "partial data"):
            pub.GitHub(runner=runner).graphql("query{viewer{login}}", {})

    def test_graphql_pagination_checks_total_duplicates_and_cursor(self):
        def page(nodes, total, more=False, cursor=None):
            return {"connection": {"nodes": nodes, "totalCount": total,
                                   "pageInfo": {"hasNextPage": more, "endCursor": cursor}}}
        api = pub.GitHub()
        api.graphql = Mock(side_effect=[page([{"id": "A"}], 2, True, "next"), page([{"id": "B"}], 2)])
        self.assertEqual([row["id"] for row in api.connection("query", {}, ("connection",))], ["A", "B"])
        for pages in ([page([{"id": "A"}], 2)],
                      [page([{"id": "A"}, {"id": "A"}], 2)],
                      [page([None], 1)],
                      [page([{"id": "A"}], 2, True, None)],
                      [page([{"id": "A"}], 2, True, "next"), page([{"id": "B"}], 3)]):
            api.graphql = Mock(side_effect=pages)
            with self.subTest(pages=pages), self.assertRaises(pub.PublicationError):
                api.connection("query", {}, ("connection",))

    def test_rest_pagination_flattens_all_pages_and_rejects_partial_shape(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '[[{"id":1}],[{"id":2}]]', ""))
        api = pub.GitHub(runner=runner)
        rows = api.rest(f"repos/{pub.REPO}/issues?per_page=100", paginate=True)
        self.assertEqual([row["id"] for row in rows], [1, 2])
        self.assertIn("--paginate", runner.call_args.args[0])
        self.assertIn("--slurp", runner.call_args.args[0])
        runner.return_value = subprocess.CompletedProcess([], 0, '[{"id":1}]', "")
        with self.assertRaisesRegex(pub.PublicationError, "pagination"):
            api.rest(f"repos/{pub.REPO}/issues?per_page=100", paginate=True)

    def test_relationship_mutations_use_numeric_ids_and_never_replace_parent(self):
        api = pub.GitHub(writable=True, delay=0)
        api.rest = Mock(return_value={})
        parent, child = {"number": 1, "id": 101}, {"number": 2, "id": 202}
        api.add_parent(parent, child)
        self.assertEqual(api.rest.call_args.args, (f"repos/{pub.REPO}/issues/1/sub_issues", "POST",
                                                 {"sub_issue_id": 202, "replace_parent": False}))
        api.add_blocker(child, parent)
        self.assertEqual(api.rest.call_args.args, (f"repos/{pub.REPO}/issues/2/dependencies/blocked_by", "POST", {"issue_id": 101}))


if __name__ == "__main__":
    unittest.main()
