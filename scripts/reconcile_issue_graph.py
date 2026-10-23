#!/usr/bin/env python3
"""Reconcile existing catalog issue types and native edges, never create issues.

The default is an offline plan check. --inspect is read-only. --apply is restricted
to the manually dispatched, fixed-repository GitHub Actions workflow. Transport,
pagination, plan validation and uncertain-write handling reuse publish_plan.py.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from publish_plan import (GitHub, Journal, PublicationError, REPO, ROOT, atomic_json,
                          digest, issue_index, issue_is_pristine, load_json,
                          publication_lock, validate_inputs, verify_relations)

REPOSITORY_ID = 1430404474
ALLOWED_ACTORS = {"CompleteDotTech", "BunsDev"}
EXTERNAL_PARENT = "https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509"


def type_name(issue):
    value = issue.get("type")
    if value is None:
        return None
    name = value.get("name") if isinstance(value, dict) else value
    if not isinstance(name, str) or not name:
        raise PublicationError("Malformed native issue type readback")
    return name


def pristine_except_type(issue, planned):
    candidate = {**issue, "type": {"name": planned["issue_type"]}}
    return (issue_is_pristine(candidate, planned) and issue.get("comments") == 0
            and issue.get("milestone") is None and issue.get("locked") is False)


def expected_counts(items):
    return {"issues": len(items), "parent_edges": sum(bool(i.get("parent_id")) for i in items),
            "blocker_edges": sum(len(i.get("blocked_by", [])) for i in items)}


def complete_nodes(connection, identity="id"):
    """The bounded bootstrap must fit one page; hidden/truncated nodes fail closed."""
    rows = connection["nodes"]
    if (not isinstance(rows, list) or connection["pageInfo"]["hasNextPage"] is not False
            or type(connection["totalCount"]) is not int or len(rows) != connection["totalCount"]
            or any(not isinstance(row, dict) or not row.get(identity) for row in rows)
            or len({row[identity] for row in rows}) != len(rows)):
        raise PublicationError("Incomplete or duplicate bounded GraphQL connection")
    return rows


def check_plan_files(payload_path, config_path, expected_hash=None):
    actual_hash = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    if expected_hash is not None and (not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
                                      or actual_hash != expected_hash):
        raise PublicationError("Expected plan SHA-256 does not match the checked-out payload")
    payload, config = load_json(payload_path), load_json(config_path)
    items = validate_inputs(payload, config)
    if payload.get("reset_existing_progress") is not False or payload.get("mutation_policy") != "create_missing_preserve_live":
        raise PublicationError("Payload does not preserve live progress")
    for relative, wanted in payload.get("source_sha256", {}).items():
        source = (ROOT / relative).resolve()
        if not source.is_relative_to(ROOT.resolve()) or not source.is_file():
            raise PublicationError("Payload source is outside the repository or missing")
        if hashlib.sha256(source.read_bytes()).hexdigest() != wanted:
            raise PublicationError(f"Payload source hash differs: {relative}")
    if not payload.get("source_sha256"):
        raise PublicationError("Payload source hashes are missing")
    return payload, config, items, actual_hash


def authorize_actions(environment):
    if (environment.get("GITHUB_ACTIONS") != "true"
            or environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or environment.get("GITHUB_REPOSITORY") != REPO
            or environment.get("GITHUB_REPOSITORY_ID") != str(REPOSITORY_ID)
            or environment.get("GITHUB_REF") != "refs/heads/main"
            or environment.get("GITHUB_ACTOR") not in ALLOWED_ACTORS
            or environment.get("GITHUB_TRIGGERING_ACTOR") not in ALLOWED_ACTORS
            or environment.get("GITHUB_RUN_ATTEMPT") != "1"
            or not re.fullmatch(r"[0-9a-f]{40}", environment.get("GITHUB_SHA", ""))):
        raise PublicationError("Apply requires a new authorized manual run on this repository's main branch")


def restore_journal(path, raw, fingerprint, items):
    """Restore an exact public receipt; unknown operation keys cannot broaden scope."""
    if not raw:
        return
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PublicationError("Resume journal contains duplicate JSON keys")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               PublicationError("Resume journal contains a non-finite value")))
    except json.JSONDecodeError as exc:
        raise PublicationError("Resume journal is not valid JSON") from exc
    allowed = {f"type:{i['id']}" for i in items}
    allowed.update(f"parent:{i['id']}" for i in items if i.get("parent_id"))
    allowed.update(f"blocker:{i['id']}:{dep}" for i in items for dep in i.get("blocked_by", []))
    if (not isinstance(value, dict) or set(value) != {"schema_version", "repository", "fingerprint", "operations"}
            or value.get("repository") != REPO
            or value.get("schema_version") != "catalog-pipeline-publication-journal-1"
            or value.get("fingerprint") != fingerprint or not isinstance(value.get("operations"), dict)
            or set(value["operations"]) - allowed):
        raise PublicationError("Resume journal does not match this exact repository and plan")
    planned = {item["id"]: item for item in items}
    for key, record in value["operations"].items():
        if (not isinstance(record, dict) or record.get("state") not in {"intent", "verified", "rejected"}
                or set(record) - {"state", "identity", "created_by_helper", "recovered_after_uncertain_write", "http_status"}):
            raise PublicationError("Resume journal contains an invalid operation receipt")
        if type(record.get("created_by_helper")) is not bool:
            raise PublicationError("Resume journal contains an invalid ownership receipt")
        if record["state"] == "verified":
            suffix = planned[key.split(":", 1)[1]]["issue_type"] if key.startswith("type:") else r"[1-9][0-9]*"
            if (not isinstance(record.get("identity"), str)
                    or not re.fullmatch(r"[1-9][0-9]*:" + suffix, record["identity"])):
                raise PublicationError("Resume journal contains an invalid operation identity")
        elif "identity" in record or record["created_by_helper"]:
            raise PublicationError("Unverified resume receipt cannot claim a completed identity")
        if "recovered_after_uncertain_write" in record and type(record["recovered_after_uncertain_write"]) is not bool:
            raise PublicationError("Resume journal recovery flag is invalid")
        if (("http_status" in record and record["state"] != "rejected")
                or ("recovered_after_uncertain_write" in record and record["state"] != "verified")):
            raise PublicationError("Resume journal fields do not match its operation state")
        if record["state"] == "rejected" and record.get("http_status") not in {400, 401, 403, 404, 409, 410, 422, 429}:
            raise PublicationError("Resume journal rejection status is invalid")
    if path.exists() and load_json(path) != value:
        raise PublicationError("Existing journal differs from the supplied receipt; refusing replacement")
    if not path.exists():
        atomic_json(path, value)


class GraphInitializer:
    def __init__(self, api, payload, config, journal=None):
        self.api, self.journal = api, journal
        self.items = validate_inputs(payload, config)
        self.planned = {item["id"]: item for item in self.items}
        self.index = {}
        self.last_readback = None

    def children(self, key):
        node = self.api.graphql("""query($id:ID!){node(id:$id){... on Issue{id
          subIssues(first:100){totalCount pageInfo{hasNextPage} nodes{id}}}}}""",
                                {"id": self.index[key]["node_id"]})["node"]
        if not node or node.get("id") != self.index[key]["node_id"]:
            raise PublicationError(f"Incomplete parent identity for {key}")
        rows = complete_nodes(node["subIssues"])
        wanted = {self.index[i["id"]]["node_id"] for i in self.items if i.get("parent_id") == key}
        observed = [row["id"] for row in rows]
        if len(observed) != len(set(observed)) or set(observed) - wanted:
            raise PublicationError(f"Unexpected native children under {key}; preserve and reconcile")
        return set(observed), wanted

    def fresh_many(self, keys, for_write=False):
        """Batch both endpoints' fresh metadata without consuming two REST requests."""
        wanted = {self.index[key]["node_id"]: key for key in keys}
        nodes = self.api.graphql("""query($ids:[ID!]!){nodes(ids:$ids){... on Issue{
          id fullDatabaseId number url title body state locked repository{nameWithOwner}
          issueType{name} milestone{id} comments{totalCount} assignedActors{totalCount}
          labels(first:100){totalCount pageInfo{hasNextPage} nodes{name}}
        }}}""", {"ids": list(wanted)})["nodes"]
        if (not isinstance(nodes, list) or len(nodes) != len(wanted)
                or any(not node or node.get("id") not in wanted for node in nodes)
                or len({node["id"] for node in nodes}) != len(nodes)):
            raise PublicationError("Incomplete fresh issue metadata")
        result = {}
        for node in nodes:
            key = wanted[node["id"]]
            original = self.index[key]
            database_id = str(node["fullDatabaseId"])
            if not re.fullmatch(r"[1-9][0-9]*", database_id) or node["repository"]["nameWithOwner"] != REPO:
                raise PublicationError(f"Issue identity changed for {key}")
            assignees, comments = node["assignedActors"]["totalCount"], node["comments"]["totalCount"]
            if type(assignees) is not int or assignees < 0 or type(comments) is not int or comments < 0:
                raise PublicationError("Incomplete discussion or ownership count")
            issue = {"id": int(database_id), "node_id": node["id"], "number": node["number"],
                     "repository_url": f"https://api.github.com/repos/{node['repository']['nameWithOwner']}",
                     "html_url": node["url"], "title": node["title"], "body": node["body"],
                     "state": node["state"].lower(), "locked": node["locked"], "type": node["issueType"],
                     "milestone": node["milestone"], "comments": comments,
                     "assignees": [] if assignees == 0 else [{"occupied": True}],
                     "labels": complete_nodes(node["labels"], "name")}
            if (issue_index(self.items, [issue]).get(key) is None
                    or any(issue[name] != original[name] for name in ("id", "node_id", "number", "html_url"))):
                raise PublicationError(f"Issue identity changed for {key}")
            if type_name(issue) not in {None, self.planned[key]["issue_type"]}:
                raise PublicationError(f"Conflicting native type for {key}; preserve and reconcile")
            if for_write and not pristine_except_type(issue, self.planned[key]):
                raise PublicationError(f"Issue {key} has progressed; no bootstrap metadata is overwritten")
            result[key] = issue
        return result

    def fresh(self, key):
        return self.fresh_many([key])[key]

    def inspect(self, require_complete=False):
        repo = self.api.rest(f"repos/{REPO}")
        if (repo.get("id") != REPOSITORY_ID or repo.get("full_name") != REPO
                or repo.get("private") is not False or repo.get("archived")
                or repo.get("disabled") or repo.get("default_branch") != "main"):
            raise PublicationError("Repository identity, visibility or main branch differs")
        current = issue_index(self.items, self.api.issues())
        if set(current) != set(self.planned):
            raise PublicationError("All canonical issues must exist before graph initialization")
        if len({row["number"] for row in current.values()}) != len(current) or len({row["node_id"] for row in current.values()}) != len(current):
            raise PublicationError("Issue number or node identity is duplicated")
        for row in current.values():
            if row.get("html_url") != f"https://github.com/{REPO}/issues/{row['number']}":
                raise PublicationError("Issue URL does not match the fixed repository")
        if self.index and any(any(current[key][name] != old[name] for name in ("id", "node_id", "number", "html_url"))
                              for key, old in self.index.items()):
            raise PublicationError("Issue identity changed during initialization")
        self.index = current
        relations = verify_relations(self.api, self.items, current, require_complete=require_complete)
        for key in {i["parent_id"] for i in self.items if i.get("parent_id")}:
            actual, wanted = self.children(key)
            if require_complete and actual != wanted:
                raise PublicationError(f"Incomplete inverse children readback for {key}")
        missing_types = []
        needs_write = set()
        for item in self.items:
            actual = type_name(current[item["id"]])
            if actual is None:
                missing_types.append(item["id"])
                needs_write.add(item["id"])
            elif actual != item["issue_type"]:
                raise PublicationError(f"Conflicting native type for {item['id']}; preserve and reconcile")
        for key in relations["missing_parents"]:
            needs_write.update((key, self.planned[key]["parent_id"]))
        for child, blocker in relations["missing_blockers"]:
            needs_write.update((child, blocker))
        for key in needs_write:
            if not pristine_except_type(current[key], self.planned[key]):
                raise PublicationError(f"Issue {key} has progressed; no bootstrap metadata is overwritten")
        report = {"mode": "live-read-only", "repository": REPO, "repository_id": REPOSITORY_ID,
                "planned_counts": expected_counts(self.items),
                "observed_counts": {"issues": len(current), "parent_edges": relations["parent_edges"],
                                    "blocker_edges": relations["blocker_edges"],
                                    "typed_issues": len(current) - len(missing_types)},
                "missing_parents": relations["missing_parents"], "missing_blockers": relations["missing_blockers"],
                "missing_types": missing_types, "network_used": True, "complete_mission": False,
                "external_parent": {"url": EXTERNAL_PARENT, "mutation": "Excluded; reconcile through authorized cross-repository handoff"},
                "issues": {key: {name: row[name] for name in ("id", "node_id", "number", "html_url")} for key, row in current.items()}}
        self.last_readback = deepcopy(report)
        return report

    def apply(self):
        if self.journal is None:
            raise PublicationError("Apply requires a durable journal")
        self.inspect()  # Complete preflight before the first mutation.
        for item in self.items:
            key, child = item["id"], self.index[item["id"]]
            if item.get("parent_id"):
                parent_key = item["parent_id"]
                parent = self.index[parent_key]

                def current_parent(k=key, p=parent_key, c=child, wanted=parent):
                    actual = self.api.parents([c])[c["node_id"]]
                    self.children(p)
                    if actual and actual["id"] != wanted["node_id"]:
                        raise PublicationError(f"Concurrent parent conflict for {k}; no replacement permitted")
                    if actual:
                        return {"identity": f"{c['id']}:{wanted['id']}"}
                    self.fresh_many([k, p], for_write=True)
                    return None

                self.journal.ensure(f"parent:{key}", current_parent,
                                    lambda p=parent, c=child: self.api.add_parent(p, c))
            for blocker_key in item.get("blocked_by", []):
                blocker = self.index[blocker_key]
                allowed = {self.index[dep]["id"] for dep in item["blocked_by"]}

                def current_blocker(k=key, b=blocker_key, c=child, wanted=blocker, expected=allowed):
                    observed = {row["id"] for row in self.api.blockers(c["number"])}
                    if observed - expected:
                        raise PublicationError(f"Concurrent blockers changed for {k}; preserve and reconcile")
                    if wanted["id"] in observed:
                        return {"identity": f"{c['id']}:{wanted['id']}"}
                    self.fresh_many([k, b], for_write=True)
                    return None

                self.journal.ensure(f"blocker:{key}:{blocker_key}", current_blocker,
                                    lambda c=child, b=blocker: self.api.add_blocker(c, b))
        for item in self.items:
            key, issue = item["id"], self.index[item["id"]]

            def current_type(k=key, expected=item["issue_type"]):
                fresh = self.fresh(k)
                if type_name(fresh) == expected:
                    return {"identity": f"{fresh['id']}:{expected}"}
                if not pristine_except_type(fresh, self.planned[k]):
                    raise PublicationError(f"Issue {k} has progressed; no bootstrap metadata is overwritten")
                return None

            self.journal.ensure(f"type:{key}", current_type,
                                lambda n=issue["number"], t=item["issue_type"]:
                                self.api.rest(f"repos/{REPO}/issues/{n}", "PATCH", {"type": t}))
        report = self.inspect(require_complete=True)
        if report["missing_types"]:
            raise PublicationError("Native type readback is incomplete")
        report.update(mode="applied-and-read-back", graph_complete=True)
        return report


def emit_receipt(report, journal=None):
    public = {**report, "journal": deepcopy(journal.data) if journal else None}
    if journal:
        public["operation_receipt_counts"] = {
            state: sum(record.get("state") == state for record in journal.data["operations"].values())
            for state in ("verified", "intent", "rejected")}
    print(json.dumps(public, indent=2))
    if journal:
        print("RESUME_JOURNAL_JSON=" + json.dumps(journal.data, separators=(",", ":")))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## Catalog issue graph readback\n\n```json\n")
            stream.write(json.dumps(public, indent=2))
            stream.write("\n```\n\nThis receipt covers issue metadata and native edges only. It does not establish Project configuration, implementation acceptance, or production deployment.\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--inspect", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".state/issue-graph")
    parser.add_argument("--write-delay", type=float, default=2.0)
    args = parser.parse_args(argv)
    journal = None
    initializer = None
    try:
        if args.apply and args.expected_plan_sha256 is None:
            raise PublicationError("Apply requires --expected-plan-sha256 for the reviewed payload")
        payload, config, items, plan_hash = check_plan_files(
            ROOT / "planning/github-issue-payloads.json", ROOT / "planning/project-config.json", args.expected_plan_sha256)
        if not args.inspect and not args.apply:
            emit_receipt({"mode": "offline-dry-run", "repository": REPO, "plan_sha256": plan_hash,
                          "planned_counts": expected_counts(items), "network_used": False, "complete_mission": False})
            return 0
        if not 1.0 <= args.write_delay <= 60:
            raise PublicationError("Write delay must be between one and sixty seconds")
        if args.apply:
            authorize_actions(os.environ)
        api = GitHub(writable=args.apply, delay=args.write_delay)
        if args.inspect:
            emit_receipt({**GraphInitializer(api, payload, config).inspect(), "plan_sha256": plan_hash})
            return 0
        head = api.rest(f"repos/{REPO}/git/ref/heads/main")
        if head.get("object", {}).get("sha") != os.environ["GITHUB_SHA"]:
            raise PublicationError("Main advanced after dispatch; review the new commit and start a new run")
        with publication_lock(args.state_dir):
            path = args.state_dir / "journal.json"
            fingerprint = digest({"payload": payload, "config": config})
            restore_journal(path, os.environ.get("GRAPH_RESUME_JOURNAL", ""), fingerprint, items)
            journal = Journal(path, fingerprint)
            initializer = GraphInitializer(api, payload, config, journal)
            report = initializer.apply()
            report["plan_sha256"] = plan_hash
            report["commit"] = os.environ["GITHUB_SHA"]
            atomic_json(args.state_dir / "readback.json", report)
            emit_receipt(report, journal)
        return 0
    except (PublicationError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        emit_receipt({"mode": "stopped", "error": str(exc), "graph_complete": False, "complete_mission": False,
                      "last_complete_readback_before_stop": initializer.last_readback if initializer else None,
                      "readback_caution": "The last full readback predates any later partial mutations; reconcile the journal with live state."}, journal)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
