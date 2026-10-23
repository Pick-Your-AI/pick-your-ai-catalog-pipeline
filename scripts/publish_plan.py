#!/usr/bin/env python3
"""Append-only GitHub setup through an already authenticated gh CLI.

Default: offline dry-run, no subprocess or network. --inspect reads live state.
--apply creates/reconciles resources and keeps a durable local journal. It never
uploads repository contents, merges, changes permissions, or claims UI acceptance.

API references checked 2026-10-22:
https://docs.github.com/en/rest/issues/sub-issues
https://docs.github.com/en/rest/issues/issue-dependencies
https://docs.github.com/en/graphql/reference/projects
https://docs.github.com/en/rest/repos/repos#create-an-organization-repository
https://docs.github.com/en/rest/issues/issues#create-an-issue
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
OWNER = "Pick-Your-AI"
NAME = "pick-your-ai-catalog-pipeline"
REPO = f"{OWNER}/{NAME}"
TITLE = "Pick Your AI — Catalog Pipeline"
API_VERSION = "2026-03-10"
KEY = r"CP(?:-[0-9]{2}(?:\.[0-9]{2})?)?"
MARKER = re.compile(r"<!-- pick-your-ai-catalog-pipeline:(" + KEY + r") -->")
MAX_PAGES = 100
PENDING = [
    "Submit repository contents through a branch and independently approved PR; this helper never pushes or merges.",
    "Verify main, repository topics/settings, team grants, CODEOWNERS, rulesets, required checks and hosted CI for the delivered revision.",
    "Configure/reload the eight saved views and verify their layout, grouping, filters and complete membership.",
    "Reconcile the program's external research #509 parent through the authorized cross-repository handoff.",
    "Reconcile any reported Project metadata, issue content/type/labels or live field differences without resetting progress.",
]


class PublicationError(ValueError):
    """A conflict or incomplete read prevents safe publication."""


class RemoteError(PublicationError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def load_json(path: Path) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PublicationError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          PublicationError(f"Non-finite JSON value: {value}")))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise PublicationError("Refusing a symlink receipt destination")
    fd, name = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def publication_lock(directory: Path):
    """One publisher per checkout; never remove another publisher's lock."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "publisher.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PublicationError("Publisher lock exists; verify the previous process before removing a stale lock") from exc
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def assert_acyclic(graph: dict[str, list[str]], label: str) -> None:
    active, done = set(), set()
    def visit(node):
        if node in active:
            raise PublicationError(f"{label} cycle at {node}")
        if node in done:
            return
        active.add(node)
        for other in graph[node]:
            if other not in graph:
                raise PublicationError(f"Unknown {label} reference {other}")
            visit(other)
        active.remove(node)
        done.add(node)
    for node in graph:
        visit(node)


def validate_inputs(payload: dict, config: dict) -> list[dict]:
    if payload.get("repository") != REPO or config.get("repository") != REPO:
        raise PublicationError("This publisher is restricted to the catalog-pipeline repository")
    if config.get("owner") != OWNER or config.get("title") != TITLE or config.get("public") is not True:
        raise PublicationError("Unexpected organization, Project title or visibility")
    fields = config.get("fields", [])
    names = [field.get("name") for field in fields]
    if not fields or len(names) != len(set(names)) or "Status" not in names or "Owner" in names:
        raise PublicationError("Invalid or duplicate Project field catalog")
    options = {}
    for field in fields:
        values = field.get("options", [])
        if field.get("type") != "SINGLE_SELECT" or not values or any(not isinstance(v, str) or not v.strip() for v in values):
            raise PublicationError("Only explicitly configured nonempty single-select fields are supported")
        if len(values) != len(set(values)):
            raise PublicationError(f"Duplicate options for {field['name']}")
        options[field["name"]] = set(values)
    items = payload.get("items", [])
    ids = [item.get("id") for item in items]
    if not items or len(ids) != len(set(ids)) or ids.count("CP") != 1:
        raise PublicationError("Missing program or duplicate stable issue IDs")
    for item in items:
        key = item.get("id", "")
        if not isinstance(key, str) or not re.fullmatch(KEY, key):
            raise PublicationError("Invalid stable ID")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise PublicationError(f"Missing title for {key}")
        body = item.get("body", "")
        if not isinstance(body, str) or MARKER.findall(body) != [key]:
            raise PublicationError(f"Expected exactly one stable marker for {key}")
        if re.search(r"(?<![\w./])@[A-Za-z0-9][A-Za-z0-9_-]*(?:/[A-Za-z0-9_-]+)?", body):
            raise PublicationError(f"Issue body {key} contains an unsolicited mention")
        if item.get("assignees", []) or item.get("issue_type") not in {"Feature", "Task"}:
            raise PublicationError(f"Invalid issue type or invented assignment for {key}")
        parent = item.get("parent_id")
        if key == "CP" and parent is not None:
            raise PublicationError("The external research parent is a separate handoff")
        if key != "CP" and parent != ("CP" if "." not in key else key.split(".")[0]):
            raise PublicationError(f"Unexpected hierarchy parent for {key}")
        deps = item.get("blocked_by", [])
        if not isinstance(deps, list) or len(deps) != len(set(deps)):
            raise PublicationError(f"Invalid dependency list for {key}")
        values = item.get("project_fields", {})
        if set(values) != set(options) or any(value not in options[name] for name, value in values.items()):
            raise PublicationError(f"Unknown/missing Project value for {key}")
        if not isinstance(item.get("labels", []), list) or any(not isinstance(v, str) for v in item.get("labels", [])):
            raise PublicationError(f"Invalid labels for {key}")
    assert_acyclic({i["id"]: [i["parent_id"]] if i.get("parent_id") else [] for i in items}, "parent")
    assert_acyclic({i["id"]: i.get("blocked_by", []) for i in items}, "dependency")
    by_id = {item["id"]: item for item in items}
    phases = next((field["options"] for field in fields if field["name"] == "Release Phase"), [])
    phase_order = {name: position for position, name in enumerate(phases)}
    for item in items:
        ancestors, parent = set(), item.get("parent_id")
        while parent:
            ancestors.add(parent)
            parent = by_id[parent].get("parent_id")
        if ancestors.intersection(item.get("blocked_by", [])):
            raise PublicationError(f"Ancestor dependency would deadlock completion of {item['id']}")
        if phases and any(phase_order[by_id[dep]["project_fields"]["Release Phase"]] >
                          phase_order[item["project_fields"]["Release Phase"]] for dep in item.get("blocked_by", [])):
            raise PublicationError(f"Later-phase prerequisite for {item['id']}")
    return items


def issue_index(items: list[dict], issues: list[dict]) -> dict[str, dict]:
    expected = {item["id"] for item in items}
    titles = {item["title"] for item in items}
    result, observed_ids = {}, set()
    for issue in issues:
        if "pull_request" in issue:
            continue
        if issue.get("repository_url") != f"https://api.github.com/repos/{REPO}":
            raise PublicationError("Issue inventory contains a foreign repository")
        if (not isinstance(issue.get("id"), int) or issue["id"] < 1 or
                not isinstance(issue.get("number"), int) or issue["number"] < 1 or
                not isinstance(issue.get("node_id"), str) or not issue["node_id"]):
            raise PublicationError("Issue inventory lacks a stable numeric/node identity")
        if issue.get("id") in observed_ids:
            raise PublicationError("Duplicate issue identity in paginated inventory")
        observed_ids.add(issue.get("id"))
        markers = MARKER.findall(issue.get("body") or "")
        if len(markers) > 1:
            raise PublicationError("Multiple plan markers on an existing issue")
        if markers:
            key = markers[0]
            if key not in expected or key in result:
                raise PublicationError(f"Unknown or duplicate existing plan marker {key}")
            result[key] = issue
        elif issue.get("title") in titles:
            raise PublicationError("A matching unmarked issue requires explicit reconciliation")
    return result


def issue_is_pristine(issue: dict, planned: dict) -> bool:
    """A receipt alone does not mean an issue has no subsequent human progress."""
    issue_type = issue.get("type")
    type_name = issue_type.get("name") if isinstance(issue_type, dict) else issue_type
    if not isinstance(issue.get("assignees"), list) or not isinstance(issue.get("labels"), list):
        return False
    labels = issue["labels"]
    names = [label.get("name") if isinstance(label, dict) else label for label in labels]
    return (issue.get("state") == "open" and issue.get("title") == planned["title"] and
            issue.get("body") == planned["body"] and not issue.get("assignees") and
            type_name == planned["issue_type"] and set(names) == set(planned.get("labels", [])))


def choose_project(projects: list[dict]) -> dict | None:
    candidates = []
    normalized = re.sub(r"[^a-z0-9]", "", TITLE.lower())
    for project in projects:
        linked = project.get("repositories", [])
        title = project.get("title", "")
        if title == TITLE or REPO in linked or re.sub(r"[^a-z0-9]", "", title.lower()) == normalized:
            candidates.append(project)
    if len(candidates) > 1:
        raise PublicationError("Multiple equivalent Projects; refusing to create or choose a duplicate")
    if not candidates:
        return None
    candidate = candidates[0]
    if candidate.get("title") != TITLE or candidate.get("closed"):
        raise PublicationError("Equivalent or closed Project requires deliberate reconciliation")
    return candidate


class Journal:
    """Intent is persisted before a write. Unknown outcomes are never retried."""
    def __init__(self, path: Path, fingerprint: str):
        self.path = path
        self.data = load_json(path) if path.exists() else {
            "schema_version": "catalog-pipeline-publication-journal-1",
            "repository": REPO, "fingerprint": fingerprint, "operations": {}}
        if self.data.get("repository") != REPO or self.data.get("fingerprint") != fingerprint:
            raise PublicationError("Journal belongs to another repository or changed baseline; reconcile it explicitly")

    def owns(self, key: str) -> bool:
        record = self.data["operations"].get(key, {})
        return record.get("state") == "verified" and record.get("created_by_helper") is True

    def ensure(self, key: str, observe: Callable, mutate: Callable) -> tuple[dict, bool]:
        operations = self.data["operations"]
        record = operations.get(key)
        current = observe()
        if current is not None:
            identity = str(current["identity"])
            if record and record.get("identity") is not None and str(record["identity"]) != identity:
                raise PublicationError(f"Remote identity changed for {key}")
            if record and record.get("state") == "intent":
                operations[key] = {"state": "verified", "identity": identity,
                                   "created_by_helper": False, "recovered_after_uncertain_write": True}
                atomic_json(self.path, self.data)
            return current, self.owns(key)
        if record and record.get("state") in {"intent", "verified"}:
            raise PublicationError(f"Uncertain or disappeared operation {key}; do not retry or discard its receipt")
        operations[key] = {"state": "intent", "created_by_helper": False}
        atomic_json(self.path, self.data)
        try:
            mutate()
        except RemoteError as exc:
            if exc.status in {400, 401, 403, 404, 409, 410, 422, 429}:
                operations[key] = {"state": "rejected", "http_status": exc.status, "created_by_helper": False}
                atomic_json(self.path, self.data)
            raise
        current = observe()
        if current is None:
            raise PublicationError(f"Write for {key} has no confirmed readback; retain its uncertain receipt")
        operations[key] = {"state": "verified", "identity": str(current["identity"]), "created_by_helper": True}
        atomic_json(self.path, self.data)
        return current, True


class GitHub:
    """No token acquisition, shell interpolation, login or approval bypass."""
    def __init__(self, writable=False, delay=1.0, runner=subprocess.run):
        self.writable, self.delay, self.runner = writable, delay, runner
        self.last_write = 0.0

    def run(self, args: list[str], data=None, mutation=False):
        if mutation and not self.writable:
            raise PublicationError("A read-only invocation attempted a mutation")
        if mutation:
            time.sleep(max(0.0, self.delay - (time.monotonic() - self.last_write)))
        environment = os.environ.copy()
        environment.update({"GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "GIT_TERMINAL_PROMPT": "0"})
        try:
            result = self.runner(["gh", *args], input=None if data is None else json.dumps(data, ensure_ascii=False),
                                 text=True, capture_output=True, timeout=60, check=False, env=environment)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RemoteError("gh is unavailable or timed out; no credentials or raw output were retained") from exc
        if mutation:
            self.last_write = time.monotonic()
        if result.returncode:
            match = re.search(r"\bHTTP (\d{3})\b", result.stderr or "")
            status = int(match.group(1)) if match else None
            raise RemoteError(f"gh request failed (exit {result.returncode}, HTTP {status or 'unknown'}); inspect the authenticated CLI separately", status)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RemoteError("gh returned non-JSON output; refusing incomplete readback") from exc
        if isinstance(value, dict) and value.get("errors"):
            raise RemoteError("GraphQL returned errors or partial data; no mutation follows")
        return value

    def rest(self, endpoint: str, method="GET", data=None, paginate=False):
        repository_path = endpoint == f"repos/{REPO}" or endpoint.startswith(f"repos/{REPO}/")
        membership_path = endpoint == f"user/memberships/orgs/{OWNER}"
        if not (repository_path or membership_path or endpoint.startswith(f"orgs/{OWNER}/")):
            raise PublicationError("REST path outside the fixed organization/repository")
        if any(part in {".", ".."} for part in endpoint.split("?", 1)[0].split("/")) or "%" in endpoint:
            raise PublicationError("Encoded or relative API paths are not permitted")
        if method != "GET" and not (endpoint == f"orgs/{OWNER}/repos" or endpoint.startswith(f"repos/{REPO}/")):
            raise PublicationError("Mutation outside the target repository")
        args = ["api", "--hostname", "github.com", "--method", method, "-H", "Accept: application/vnd.github+json",
                "-H", f"X-GitHub-Api-Version: {API_VERSION}", endpoint]
        if data is not None:
            args += ["--input", "-"]
        if paginate:
            args += ["--paginate", "--slurp"]
        value = self.run(args, data, mutation=method != "GET")
        if not paginate:
            return value
        if not isinstance(value, list) or len(value) > MAX_PAGES or any(not isinstance(page, list) for page in value):
            raise PublicationError("Malformed or excessive REST pagination")
        return [item for page in value for item in page]

    def graphql(self, query: str, variables: dict):
        mutation = query.lstrip().startswith("mutation")
        value = self.run(["api", "--hostname", "github.com", "graphql", "--input", "-"],
                         {"query": query, "variables": variables}, mutation=mutation)
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            raise PublicationError("Missing GraphQL data")
        return value["data"]

    def connection(self, query: str, variables: dict, path: tuple[str, ...]):
        result, cursor, seen = [], None, set()
        total = None
        for _ in range(MAX_PAGES):
            data = self.graphql(query, {**variables, "cursor": cursor})
            try:
                for part in path:
                    data = data[part]
                nodes, info, current_total = data["nodes"], data["pageInfo"], data["totalCount"]
            except (KeyError, TypeError) as exc:
                raise PublicationError("Incomplete GraphQL connection") from exc
            if any(node is None for node in nodes) or (total is not None and current_total != total):
                raise PublicationError("Hidden nodes or concurrent inventory change; repeat read-only discovery")
            total = current_total
            result.extend(nodes)
            if not info["hasNextPage"]:
                if len(result) != total or len({node["id"] for node in result}) != len(result):
                    raise PublicationError("Truncated or duplicate GraphQL inventory")
                return result
            cursor = info.get("endCursor")
            if not cursor or cursor in seen:
                raise PublicationError("Invalid pagination cursor")
            seen.add(cursor)
        raise PublicationError("GraphQL page limit reached; inventory is incomplete")

    def repositories(self):
        return self.rest(f"orgs/{OWNER}/repos?type=all&per_page=100&sort=full_name&direction=asc", paginate=True)

    def repo(self):
        matches = [row for row in self.repositories() if row.get("full_name", "").lower() == REPO.lower()]
        if len(matches) > 1:
            raise PublicationError("Duplicate repository identity")
        if not matches:
            return None
        row = matches[0]
        if row.get("private") or row.get("archived") or row.get("disabled"):
            raise PublicationError("Existing repository is private, archived or disabled; no settings changed")
        return {**row, "identity": row["id"]}

    def projects(self):
        rows = self.connection("""query($owner:String!,$cursor:String){organization(login:$owner){
          projectsV2(first:100,after:$cursor){totalCount pageInfo{hasNextPage endCursor}
          nodes{id number title shortDescription public closed url viewerCanUpdate
          repositories(first:100){totalCount pageInfo{hasNextPage} nodes{nameWithOwner}}}}}}""",
                               {"owner": OWNER}, ("organization", "projectsV2"))
        for row in rows:
            nested = row["repositories"]
            if nested["pageInfo"]["hasNextPage"] or len(nested["nodes"]) != nested["totalCount"]:
                raise PublicationError("Incomplete Project repository-link inventory")
            row["repositories"] = [node["nameWithOwner"] for node in nested["nodes"]]
            row["identity"] = row["id"]
        return rows

    def project(self):
        return choose_project(self.projects())

    def issues(self):
        return self.rest(f"repos/{REPO}/issues?state=all&per_page=100&sort=created&direction=asc", paginate=True)

    def issue(self, number):
        return self.rest(f"repos/{REPO}/issues/{int(number)}")

    def parents(self, issues):
        ids = [issue["node_id"] for issue in issues]
        result = {}
        for start in range(0, len(ids), 100):
            batch = ids[start:start + 100]
            data = self.graphql("""query($ids:[ID!]!){nodes(ids:$ids){... on Issue{id
              parent{id url number repository{nameWithOwner}}}}}""", {"ids": batch})["nodes"]
            if (len(data) != len(batch) or any(not node or node.get("id") not in batch for node in data)
                    or len({node["id"] for node in data if node}) != len(batch)):
                raise PublicationError("Incomplete native-parent read")
            result.update({node["id"]: node["parent"] for node in data})
        return result

    def blockers(self, number):
        return self.rest(f"repos/{REPO}/issues/{int(number)}/dependencies/blocked_by?per_page=100", paginate=True)

    def fields(self, project):
        return self.connection("""query($id:ID!,$cursor:String){node(id:$id){... on ProjectV2{
          fields(first:100,after:$cursor){totalCount pageInfo{hasNextPage endCursor} nodes{
          ... on ProjectV2Field{id name dataType}
          ... on ProjectV2SingleSelectField{id name dataType options{id name color description}}
          ... on ProjectV2IterationField{id name dataType}}}}}}""", {"id": project["id"]}, ("node", "fields"))

    def project_items(self, project):
        rows = self.connection("""query($id:ID!,$cursor:String){node(id:$id){... on ProjectV2{
          items(first:100,after:$cursor){totalCount pageInfo{hasNextPage endCursor} nodes{id isArchived
          content{__typename ... on Issue{id number url repository{nameWithOwner}}}
          fieldValues(first:100){totalCount pageInfo{hasNextPage} nodes{
          ... on ProjectV2ItemFieldSingleSelectValue{name optionId field{
          ... on ProjectV2SingleSelectField{id name}}}}}}}}}}""", {"id": project["id"]}, ("node", "items"))
        for row in rows:
            nested = row["fieldValues"]
            if nested["pageInfo"]["hasNextPage"] or len(nested["nodes"]) != nested["totalCount"]:
                raise PublicationError("Incomplete item-field readback")
            row["values"] = {node["field"]["name"]: node["name"] for node in nested["nodes"] if "field" in node}
            row["identity"] = row["id"]
        return rows

    def create_repository(self, config):
        metadata = config.get("repository_metadata", {})
        return self.rest(f"orgs/{OWNER}/repos", "POST", {
            "name": NAME, "private": False, "auto_init": True, "has_issues": True,
            "has_wiki": False, "description": metadata.get("description", config["description"])})

    def create_project(self):
        return self.run(["project", "create", "--owner", OWNER, "--title", TITLE, "--format", "json"], mutation=True)

    def initialize_project(self, project, config):
        return self.graphql("""mutation($input:UpdateProjectV2Input!){updateProjectV2(input:$input){projectV2{id}}}""",
                            {"input": {"projectId": project["id"], "public": True, "shortDescription": config["description"]}})

    def link_project(self, project, repo):
        return self.graphql("""mutation($input:LinkProjectV2ToRepositoryInput!){linkProjectV2ToRepository(input:$input){repository{id}}}""",
                            {"input": {"projectId": project["id"], "repositoryId": repo["node_id"]}})

    def create_field(self, project, field):
        return self.graphql("""mutation($input:CreateProjectV2FieldInput!){createProjectV2Field(input:$input){
          projectV2Field{... on ProjectV2SingleSelectField{id}}}}""", {"input": {
              "projectId": project["id"], "name": field["name"], "dataType": "SINGLE_SELECT",
              "singleSelectOptions": [{"name": name, "color": "GRAY", "description": ""} for name in field["options"]]}})

    def initialize_status(self, field, options):
        return self.graphql("""mutation($input:UpdateProjectV2FieldInput!){updateProjectV2Field(input:$input){
          projectV2Field{... on ProjectV2SingleSelectField{id}}}}""", {"input": {
              "fieldId": field["id"], "singleSelectOptions": [
                  {"name": name, "color": "GRAY", "description": "", **({"id": old["id"]} if old else {})}
                  for name in options for old in [next((o for o in field["options"] if o["name"] == name), None)]]}})

    def create_issue(self, item):
        data = {"title": item["title"], "body": item["body"], "type": item["issue_type"]}
        if item.get("labels"):
            data["labels"] = item["labels"]
        return self.rest(f"repos/{REPO}/issues", "POST", data)

    def add_parent(self, parent, child):
        return self.rest(f"repos/{REPO}/issues/{parent['number']}/sub_issues", "POST",
                         {"sub_issue_id": child["id"], "replace_parent": False})

    def add_blocker(self, issue, blocker):
        return self.rest(f"repos/{REPO}/issues/{issue['number']}/dependencies/blocked_by", "POST",
                         {"issue_id": blocker["id"]})

    def add_item(self, project, issue):
        return self.graphql("""mutation($input:AddProjectV2ItemByIdInput!){addProjectV2ItemById(input:$input){item{id}}}""",
                            {"input": {"projectId": project["id"], "contentId": issue["node_id"]}})

    def set_value(self, project, item, field, option):
        return self.graphql("""mutation($input:UpdateProjectV2ItemFieldValueInput!){updateProjectV2ItemFieldValue(input:$input){projectV2Item{id}}}""",
                            {"input": {"projectId": project["id"], "itemId": item["id"], "fieldId": field["id"],
                                       "value": {"singleSelectOptionId": option["id"]}}})


def unique_by(rows, key, label):
    result = {}
    for row in rows:
        name = row[key]
        if name in result:
            raise PublicationError(f"Duplicate {label}: {name}")
        result[name] = row
    return result


def field_map(api, project):
    result = unique_by(api.fields(project), "name", "field name")
    for field in result.values():
        field["identity"] = field["id"]
        if "options" in field:
            unique_by(field["options"], "name", "field option")
    return result


def verify_fields(fields, configured):
    for expected in configured:
        actual = fields.get(expected["name"])
        if (not actual or actual.get("dataType") != "SINGLE_SELECT" or
                not set(expected["options"]) <= {option["name"] for option in actual.get("options", [])}):
            raise PublicationError(f"Incomplete or conflicting Project field {expected['name']}")


def item_map(api, project):
    result = {}
    for item in api.project_items(project):
        content = item.get("content")
        if not content or content.get("__typename") != "Issue" or content.get("repository", {}).get("nameWithOwner") != REPO:
            continue
        key = content["id"]
        if key in result:
            raise PublicationError("Duplicate Project membership for an issue")
        if item.get("isArchived"):
            raise PublicationError("Archived target Project item requires deliberate reconciliation")
        result[key] = item
    return result


def verify_relations(api, items, index, require_complete=False):
    parents = api.parents(list(index.values()))
    summary = {"parent_edges": 0, "blocker_edges": 0, "missing_parents": [], "missing_blockers": []}
    for item in items:
        key = item["id"]
        if key not in index:
            if require_complete:
                raise PublicationError(f"Missing issue {key} in final readback")
            continue
        issue = index[key]
        actual_parent = parents[issue["node_id"]]
        parent_key = item.get("parent_id")
        desired = index.get(parent_key)
        if actual_parent and (not desired or actual_parent["id"] != desired["node_id"]):
            if key != "CP" or actual_parent.get("url") != "https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509":
                raise PublicationError(f"Conflicting native parent for {key}; never force-reparent")
        if parent_key and not actual_parent:
            summary["missing_parents"].append(key)
        elif parent_key:
            summary["parent_edges"] += 1
        actual = api.blockers(issue["number"])
        actual_ids = {row["id"] for row in actual}
        wanted = {index[dep]["id"] for dep in item.get("blocked_by", []) if dep in index}
        if actual_ids - wanted:
            raise PublicationError(f"Unexpected native blockers for {key}; preserve and reconcile before adding edges")
        for dep in item.get("blocked_by", []):
            if dep not in index or index[dep]["id"] not in actual_ids:
                summary["missing_blockers"].append([key, dep])
            else:
                summary["blocker_edges"] += 1
    if require_complete and (summary["missing_parents"] or summary["missing_blockers"]):
        raise PublicationError("Final native-relationship readback is incomplete")
    return summary


class Publisher:
    def __init__(self, api, payload, config, journal):
        self.api, self.payload, self.config, self.journal = api, payload, config, journal
        self.items = validate_inputs(payload, config)
        self.preserved = []

    def inspect(self):
        repo, project = self.api.repo(), self.api.project()
        index = issue_index(self.items, self.api.issues()) if repo else {}
        labels = unique_by(self.api.rest(f"repos/{REPO}/labels?per_page=100", paginate=True), "name", "label") if repo else {}
        relations = verify_relations(self.api, self.items, index) if repo else None
        fields = field_map(self.api, project) if project else {}
        members = item_map(self.api, project) if project else {}
        return {"repository": repo, "project": project, "issue_index": index,
                "fields": fields, "members": members, "relations": relations, "labels": labels}

    def apply(self):
        # Complete discovery of the automated scope before the first mutation.
        before = self.inspect()
        if before["project"] and not before["project"].get("viewerCanUpdate"):
            raise PublicationError("Project is not writable; no resource mutation started")
        if before["project"] and not before["project"].get("public") and not self.journal.owns("project"):
            raise PublicationError("Existing Project is private; its visibility will not be changed")
        for expected in self.config["fields"]:
            actual = before["fields"].get(expected["name"])
            if actual and (actual.get("dataType") != "SINGLE_SELECT" or
                           not set(expected["options"]) <= {o["name"] for o in actual.get("options", [])}):
                if not (expected["name"] == "Status" and self.journal.owns("project") and not before["members"]):
                    raise PublicationError(f"Existing field {expected['name']} needs manual configuration; no values/options overwritten")
        repo, _ = self.journal.ensure("repository", self.api.repo, lambda: self.api.create_repository(self.config))
        if repo.get("default_branch") != "main":
            raise PublicationError("Repository default branch is not main; content/default-branch submission remains separate")
        project, _ = self.journal.ensure("project", self.api.project, self.api.create_project)
        if not project.get("viewerCanUpdate"):
            raise PublicationError("Project became read-only; no further mutation permitted")
        if not project.get("public") and not self.journal.owns("project"):
            raise PublicationError("Recovered Project ownership is uncertain; private visibility is preserved")
        if self.journal.owns("project"):
            def configured_project():
                current = self.api.project()
                return current if current and current.get("public") and current.get("shortDescription") == self.config["description"] else None
            project, _ = self.journal.ensure("project-metadata", configured_project,
                                             lambda: self.api.initialize_project(project, self.config))
        def linked_project():
            current = self.api.project()
            return current if current and REPO in current.get("repositories", []) else None
        self.journal.ensure("project-repository-link", linked_project, lambda: self.api.link_project(project, repo))
        for expected in self.config["fields"]:
            name = expected["name"]
            actual = field_map(self.api, project).get(name)
            if name == "Status" and actual and not set(expected["options"]) <= {o["name"] for o in actual["options"]}:
                if not self.journal.owns("project") or self.api.project_items(project):
                    raise PublicationError("Status can be initialized only on this helper's empty new Project")
                def configured_status():
                    field = field_map(self.api, project).get("Status")
                    return field if field and [o["name"] for o in field["options"]] == expected["options"] else None
                self.journal.ensure("status-options", configured_status,
                                    lambda: self.api.initialize_status(actual, expected["options"]))
            else:
                if name == "Status" and actual is None:
                    raise PublicationError("Native Status missing; refusing to create a duplicate Status field")
                self.journal.ensure(f"field:{name}", lambda n=name: field_map(self.api, project).get(n),
                                    lambda f=expected: self.api.create_field(project, f))
        verify_fields(field_map(self.api, project), self.config["fields"])
        for label in self.config.get("labels", []):
            def current_label(name=label["name"]):
                rows = self.api.rest(f"repos/{REPO}/labels?per_page=100", paginate=True)
                row = unique_by(rows, "name", "label").get(name)
                return {**row, "identity": row["id"]} if row else None
            self.journal.ensure(f"label:{label['name']}", current_label,
                                lambda value=label: self.api.rest(f"repos/{REPO}/labels", "POST", value))
        for item in self.items:
            def current_issue(key=item["id"]):
                row = issue_index(self.items, self.api.issues()).get(key)
                return {**row, "identity": row["id"]} if row else None
            self.journal.ensure(f"issue:{item['id']}", current_issue, lambda value=item: self.api.create_issue(value))
        index = issue_index(self.items, self.api.issues())
        verify_relations(self.api, self.items, index)
        for item in self.items:
            issue = index[item["id"]]
            if item.get("parent_id"):
                parent = index[item["parent_id"]]
                def current_parent(child=issue, wanted=parent):
                    value = self.api.parents([child])[child["node_id"]]
                    if value and value["id"] != wanted["node_id"]:
                        raise PublicationError("Concurrent parent changed; no replacement permitted")
                    return {"identity": f"{child['id']}:{wanted['id']}"} if value else None
                self.journal.ensure(f"parent:{item['id']}", current_parent,
                                    lambda p=parent, c=issue: self.api.add_parent(p, c))
            for key in item.get("blocked_by", []):
                blocker = index[key]
                expected_blockers = {index[other]["id"] for other in item["blocked_by"]}
                def current_blocker(child=issue, wanted=blocker, allowed=expected_blockers):
                    observed = {row["id"] for row in self.api.blockers(child["number"])}
                    if observed - allowed:
                        raise PublicationError("Concurrent native blockers changed; reconcile before adding edges")
                    found = wanted["id"] in observed
                    return {"identity": f"{child['id']}:{wanted['id']}"} if found else None
                self.journal.ensure(f"blocker:{item['id']}:{key}", current_blocker,
                                    lambda c=issue, b=blocker: self.api.add_blocker(c, b))
        fields = field_map(self.api, project)
        verify_fields(fields, self.config["fields"])
        for item in self.items:
            key, issue = item["id"], index[item["id"]]
            def current_member(node=issue["node_id"]):
                return item_map(self.api, project).get(node)
            member, created = self.journal.ensure(f"item:{key}", current_member,
                                                 lambda value=issue: self.api.add_item(project, value))
            fresh_issue = issue_index(self.items, [self.api.issue(issue["number"])])[key]
            if not created or not self.journal.owns(f"issue:{key}") or not issue_is_pristine(fresh_issue, item):
                self.preserved.append(key)
                continue
            for name, desired in item["project_fields"].items():
                field = fields[name]
                option = next(o for o in field["options"] if o["name"] == desired)
                current = current_member()
                actual = current["values"].get(name)
                if actual is not None and actual != desired:
                    self.preserved.append(f"{key}:{name}")
                    continue
                def current_value(n=name, wanted=desired):
                    fresh = issue_index(self.items, [self.api.issue(issue["number"])])[key]
                    if not issue_is_pristine(fresh, item):
                        raise PublicationError("Issue progressed during initialization; preserve progress and reconcile")
                    row = current_member()
                    value = row["values"].get(n)
                    if value is not None and value != wanted:
                        raise PublicationError("Concurrent field value changed; refusing overwrite")
                    return {"identity": f"{row['id']}:{n}:{wanted}"} if value == wanted else None
                self.journal.ensure(f"value:{key}:{name}", current_value,
                                    lambda m=member, f=field, o=option: self.api.set_value(project, m, f, o))
        after = self.inspect()
        if not after["project"] or not after["project"].get("public"):
            raise PublicationError("Final public Project readback is incomplete")
        if after["repository"]["id"] != repo["id"] or after["project"]["id"] != project["id"]:
            raise PublicationError("Repository or Project identity changed during publication")
        verify_fields(after["fields"], self.config["fields"])
        relations = verify_relations(self.api, self.items, after["issue_index"], require_complete=True)
        for key, issue in after["issue_index"].items():
            if issue["node_id"] not in after["members"]:
                raise PublicationError(f"Missing final Project membership for {key}")
        mismatches = []
        issue_differences = []
        for expected in self.items:
            issue = after["issue_index"][expected["id"]]
            member = after["members"][issue["node_id"]]
            actual_type = issue.get("type")
            actual_type = actual_type.get("name") if isinstance(actual_type, dict) else actual_type
            actual_labels = [label.get("name") if isinstance(label, dict) else label for label in issue.get("labels", [])]
            different = [name for name in ("title", "body") if issue.get(name) != expected[name]]
            if actual_type != expected["issue_type"]:
                different.append("issue_type")
            if set(actual_labels) != set(expected.get("labels", [])):
                different.append("labels")
            if issue.get("state") != "open":
                different.append("state")
            if issue.get("assignees"):
                different.append("assignees")
            if different:
                issue_differences.append({"id": expected["id"], "url": issue["html_url"], "fields": different,
                    "baseline_content_sha256": digest({name: expected[name] for name in ("title", "body")}),
                    "observed_content_sha256": digest({name: issue.get(name) for name in ("title", "body")}),
                    "observed_state": issue.get("state"), "observed_issue_type": actual_type,
                    "disposition": "Preserved live content and progress; issue identity alone does not prove baseline scope acceptance"})
            for name, value in expected["project_fields"].items():
                observed = member["values"].get(name)
                if observed != value:
                    mismatches.append({"id": expected["id"], "field": name, "baseline": value, "observed": observed,
                                       "disposition": "Preserved live value or uninitialized pre-existing item; requires explicit reconciliation"})
        report = {"mode": "applied-with-pending-acceptance", "repository": REPO,
                  "repository_id": after["repository"]["id"], "project": {k: after["project"][k] for k in ["id", "number", "url", "title", "public"]},
                  "issue_urls": {key: issue["html_url"] for key, issue in after["issue_index"].items()},
                  "counts": {"issues": len(after["issue_index"]), "project_items": len(self.items),
                             "parent_edges": relations["parent_edges"], "blocker_edges": relations["blocker_edges"]},
                  "preserved_existing": self.preserved, "field_differences": mismatches,
                  "issue_differences": issue_differences,
                  "project_differences": [
                      {"field": name, "baseline": wanted, "observed": observed,
                       "disposition": "Preserved existing Project configuration; explicit reconciliation pending"}
                      for name, wanted, observed in (
                          ("title", self.config["title"], after["project"].get("title")),
                          ("description", self.config["description"], after["project"].get("shortDescription")),
                          ("public", True, after["project"].get("public")),
                          ("repository_link", True, REPO in after["project"].get("repositories", [])))
                      if wanted != observed],
                  "pending": PENDING,
                  "complete_mission": False}
        atomic_json(self.journal.path.parent / "readback.json", report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--inspect", action="store_true", help="Read live GitHub state; never mutate")
    modes.add_argument("--apply", action="store_true", help="Create/reconcile through preauthenticated gh; no login or token handling")
    parser.add_argument("--payload", type=Path, default=ROOT / "planning/github-issue-payloads.json")
    parser.add_argument("--config", type=Path, default=ROOT / "planning/project-config.json")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".state/publication")
    parser.add_argument("--write-delay", type=float, default=1.0, help="Minimum seconds between writes; respect GitHub quota limits")
    args = parser.parse_args(argv)
    try:
        payload, config = load_json(args.payload), load_json(args.config)
        items = validate_inputs(payload, config)
        if not args.inspect and not args.apply:
            print(json.dumps({"mode": "offline-dry-run", "repository": REPO, "issues": len(items),
                              "parent_edges": sum(bool(i.get("parent_id")) for i in items),
                              "blocker_edges": sum(len(i.get("blocked_by", [])) for i in items),
                              "project_fields": len(config["fields"]), "network_used": False,
                              "pending": PENDING, "complete_mission": False}, indent=2))
            return 0
        if args.write_delay < 0 or args.write_delay > 60:
            raise PublicationError("Write delay must be between 0 and 60 seconds")
        api = GitHub(writable=args.apply, delay=args.write_delay)
        journal = Journal(args.state_dir / "journal.json", digest({"payload": payload, "config": config}))
        publisher = Publisher(api, payload, config, journal)
        if args.inspect:
            state = publisher.inspect()
            print(json.dumps({"mode": "live-read-only", "repository_exists": state["repository"] is not None,
                              "project": state["project"], "existing_issues": sorted(state["issue_index"]),
                              "fields": list(state["fields"]), "relationships": state["relations"],
                              "pending": PENDING, "complete_mission": False}, indent=2))
            return 0
        membership = api.rest(f"user/memberships/orgs/{OWNER}")
        if membership.get("state") != "active" or membership.get("role") != "admin":
            raise PublicationError("Setup requires an authenticated organization owner for complete administrative discovery")
        with publication_lock(args.state_dir):
            print(json.dumps(publisher.apply(), indent=2))
        return 0
    except (PublicationError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"Publication stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
