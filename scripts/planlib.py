"""Read and validate the local scope baseline; never mutate or authenticate GitHub.

Structural JSON Schema checks and standard-library cross-file checks are separate.
A well-shaped receipt is not proof that a remote review or source grant happened.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

PHASES = ("Bootstrap", "Foundation", "Bounded Pilot", "Beta", "Production", "Expansion")
STATUSES = ("Backlog", "Ready", "In Progress", "In Review", "Blocked", "Done")
PRIORITIES = ("P0", "P1", "P2", "P3")
READINESS = ("Ready", "Needs Input", "Blocked", "Awaiting Decision")
ACCEPTANCE = ("Not Started", "In Review", "Accepted", "Changes Required", "Deferred")
EVIDENCE = ("Unverified", "Low", "Medium", "High", "Not Applicable")
RIGHTS = ("Not Assessed", "Research Only", "Conditional", "Approved", "Restricted", "Revoked", "Not Applicable")
DEPENDENCIES = ("Not Assessed", "No Dependencies", "Waiting", "Ready", "Blocked")
EFFORT = ("Unknown", "S", "M", "L")
PRESERVE_FIELDS = {"assignees", "status", "readiness", "acceptance_status", "done", "comments", "approved_decisions"}
REQUIRED_DOMAINS = {"model", "offering", "hardware", "runtime", "dataset", "benchmark", "application", "agent_tool", "paper", "organization", "use_case", "trust", "cost_energy", "learning"}
REQUIRED_CONSUMERS = {"website", "apple", "android", "canonical-planner-service"}
FILES = {
    "backlog": "project-backlog.json",
    "coverage": "coverage-matrix.json",
    "decisions": "decision-register.json",
    "releases": "release-manifest.json",
}
SCHEMAS = {key: value.replace(".json", ".schema.json") for key, value in FILES.items()}
NATIVE_LEVELS = {"Program", "Epic", "Work Package"}
GITHUB_ID_KEYS = {"issue_number", "github_issue_number", "project_number", "github_project_number", "project_id", "github_project_id", "github_issue_id", "node_id", "github_node_id"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number: {token}")
    return value


def _invalid_constant(token):
    raise ValueError(f"non-finite JSON constant: {token}")


def load_json(path):
    """Reject duplicate keys, NaN/Infinity and overflowing numeric tokens."""
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                      parse_float=_finite_float, parse_constant=_invalid_constant)


def load_bundle(root):
    return {key: load_json(Path(root) / "planning" / name) for key, name in FILES.items()}


def iter_records(backlog):
    """Yield program, epics, packages, checklist tasks and subtasks in order."""
    program = backlog.get("program")
    if isinstance(program, dict):
        yield program
    for epic in backlog.get("epics", []):
        yield epic
        for package in epic.get("work_packages", []):
            yield package
            for task in package.get("tasks", []):
                yield task
                yield from task.get("subtasks", [])


def _url(value):
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(c) < 33 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None and parsed.password is None


def _timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value, re.ASCII):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def _receipt_errors(receipts, path):
    errors = []
    if not isinstance(receipts, list) or not receipts:
        return [f"{path}: actual acceptance receipts are required"]
    for i, receipt in enumerate(receipts):
        loc = f"{path}[{i}]"
        if not isinstance(receipt, dict):
            errors.append(f"{loc}: expected an attributable receipt object, not requirement prose")
            continue
        for key in ("reviewer", "scope"):
            if not isinstance(receipt.get(key), str) or not receipt[key].strip():
                errors.append(f"{loc}.{key}: nonempty text required")
        if not _url(receipt.get("url")):
            errors.append(f"{loc}.url: credential-free HTTPS receipt URL required")
        if not isinstance(receipt.get("reviewed_commit"), str) or not re.fullmatch(r"[0-9a-fA-F]{40}", receipt["reviewed_commit"]):
            errors.append(f"{loc}.reviewed_commit: full 40-character commit required")
        if not _timestamp(receipt.get("submitted_at")):
            errors.append(f"{loc}.submitted_at: timezone-aware timestamp required")
        if receipt.get("synthetic") is not False:
            errors.append(f"{loc}.synthetic: must explicitly be false for real acceptance")
    return errors


def _github_identity_errors(value, path="plan"):
    """Unknown identities stay null; observed identities need a readback envelope."""
    errors = []
    if isinstance(value, list):
        for i, child in enumerate(value):
            errors.extend(_github_identity_errors(child, f"{path}[{i}]"))
    elif isinstance(value, dict):
        present = [key for key in GITHUB_ID_KEYS if value.get(key) is not None]
        if present:
            if value.get("verified") is not True or not _timestamp(value.get("verified_at")) or not _url(value.get("readback_url")):
                errors.append(f"{path}: GitHub identities {sorted(present)} require verified readback metadata; do not invent IDs")
            for key in present:
                item = value[key]
                if key.endswith("number") or key in {"project_id", "github_project_id", "github_issue_id"}:
                    if type(item) is not int or item <= 0:
                        errors.append(f"{path}.{key}: positive integer identity required")
                elif not isinstance(item, str) or not item.strip() or item.lower() in {"unknown", "pending", "tbd", "placeholder"}:
                    errors.append(f"{path}.{key}: non-placeholder node identity required")
        for key, child in value.items():
            errors.extend(_github_identity_errors(child, f"{path}.{key}"))
    return errors


def _cycle_errors(graph):
    state, path, errors = {}, [], []

    def visit(node):
        if state.get(node) == 1:
            begin = path.index(node)
            errors.append("blocked_by dependency cycle: " + " -> ".join(path[begin:] + [node]))
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        path.append(node)
        for target in graph.get(node, []):
            if target in graph:
                visit(target)
        path.pop()
        state[node] = 2

    for node in graph:
        visit(node)
    return errors


def validate_bundle(bundle):
    """Cross-file semantics. Returns diagnostics; never writes or fetches data."""
    errors = []
    if not isinstance(bundle, dict) or any(not isinstance(bundle.get(k), dict) for k in FILES):
        return ["bundle: backlog, coverage, decisions and releases must be objects"]
    backlog, coverage, decisions, releases = (bundle[k] for k in FILES)
    program = backlog.get("program")
    if not isinstance(program, dict) or not isinstance(backlog.get("epics"), list):
        return ["backlog: program object and epics array required"]
    if not backlog["epics"]:
        errors.append("backlog.epics: at least one epic is required")
    nodes, levels, parents, children, packages, epics = {}, {}, {}, {}, {}, {}

    def add(record, level, parent=None, pattern=None):
        if not isinstance(record, dict):
            errors.append(f"{level}: record must be an object")
            return None
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{level}: stable nonempty id required")
            return None
        if identifier in nodes:
            errors.append(f"duplicate planning ID: {identifier}")
        else:
            nodes[identifier] = record
        levels[identifier] = level
        if pattern and not re.fullmatch(pattern, identifier, re.ASCII):
            errors.append(f"{identifier}: ID does not match its {level} hierarchy")
        if level != "Subtask" and record.get("level") != level:
            errors.append(f"{identifier}: level must be {level}")
        if parent is not None:
            parents[identifier] = parent
            children.setdefault(parent, []).append(identifier)
            if level in NATIVE_LEVELS and record.get("parent") != parent:
                errors.append(f"{identifier}: parent must be {parent}")
            if "parent" in record and record["parent"] != parent:
                errors.append(f"{identifier}: declared parent conflicts with containing hierarchy")
        return identifier

    pid = add(program, "Program", pattern=r"CP")
    for epic in backlog["epics"]:
        eid = add(epic, "Epic", pid, r"CP-\d{2,}")
        if eid is None:
            continue
        epics[eid] = epic
        if not isinstance(epic.get("work_packages"), list) or not epic["work_packages"]:
            errors.append(f"{eid}: at least one work package required")
            continue
        for package in epic["work_packages"]:
            wid = add(package, "Work Package", eid, re.escape(eid) + r"\.\d{2,}")
            if wid is None:
                continue
            packages[wid] = package
            if package.get("workstream") != epic.get("workstream"):
                errors.append(f"{wid}: workstream must match its epic")
            if not isinstance(package.get("tasks"), list) or not package["tasks"]:
                errors.append(f"{wid}: at least one independently specified checklist task required")
                continue
            for task in package["tasks"]:
                tid = add(task, "Task", wid, re.escape(wid) + r"\.T[1-9]\d*")
                if tid is None:
                    continue
                if not isinstance(task.get("subtasks"), list) or not task["subtasks"]:
                    errors.append(f"{tid}: at least one bounded subtask required")
                    continue
                for subtask in task["subtasks"]:
                    add(subtask, "Subtask", tid, re.escape(tid) + r"\.S[1-9]\d*")

    if len({e.get("workstream") for e in epics.values()}) != len(epics):
        errors.append("epics: workstream names must be unique")
    reconciliation = backlog.get("reconciliation", {})
    if not isinstance(reconciliation, dict) or reconciliation.get("mode") != "create_missing_preserve_live" or reconciliation.get("reset_existing_progress") is not False:
        errors.append("reconciliation: create_missing_preserve_live with reset_existing_progress=false required")
    preserved = reconciliation.get("preserve_fields", []) if isinstance(reconciliation, dict) else []
    if not isinstance(preserved, list) or not PRESERVE_FIELDS.issubset({v for v in preserved if isinstance(v, str)}):
        errors.append("reconciliation: must preserve live assignees, statuses, checklist progress, comments and approved decisions")

    enum_fields = {"status": STATUSES, "priority": PRIORITIES, "phase": PHASES, "readiness": READINESS, "acceptance_status": ACCEPTANCE,
                   "effort": EFFORT, "evidence_confidence": EVIDENCE, "source_rights_status": RIGHTS, "dependency_status": DEPENDENCIES}
    graph = {}
    for identifier, record in nodes.items():
        level = levels[identifier]
        if level in NATIVE_LEVELS:
            for key, allowed in enum_fields.items():
                if record.get(key) not in allowed:
                    errors.append(f"{identifier}.{key}: invalid value {record.get(key)!r}")
            if record.get("readiness") == "Ready" or record.get("status") == "Ready":
                if not record.get("assignees"):
                    errors.append(f"{identifier}: Ready requires an accepted native assignee")
            deps = record.get("blocked_by", [])
            if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
                errors.append(f"{identifier}.blocked_by: array of planning IDs required")
                deps = []
            if len(deps) != len(set(deps)):
                errors.append(f"{identifier}.blocked_by: duplicate prerequisite")
            graph[identifier] = deps
            if deps and record.get("dependency_status") == "No Dependencies":
                errors.append(f"{identifier}: No Dependencies conflicts with blocked_by")
            if not deps and record.get("dependency_status") in {"Blocked", "Waiting"}:
                aggregate_wait = (level in {"Program", "Epic"} and record.get("dependency_status") == "Waiting"
                                  and any(nodes[child].get("status") != "Done" for child in children.get(identifier, [])))
                if not aggregate_wait:
                    errors.append(f"{identifier}: dependency status requires a recorded prerequisite or unfinished aggregate child")
            for dep in deps:
                if dep not in nodes or levels.get(dep) not in NATIVE_LEVELS:
                    errors.append(f"{identifier}: missing or non-native blocked_by target {dep}")
                    continue
                if dep == identifier:
                    errors.append(f"{identifier}: cannot block itself")
                ancestor = parents.get(identifier)
                ancestors = set()
                while ancestor is not None and ancestor not in ancestors:
                    ancestors.add(ancestor)
                    ancestor = parents.get(ancestor)
                if dep in ancestors:
                    errors.append(f"{identifier}: cannot wait on ancestor {dep}, whose completion already includes this child")
                dep_phase, own_phase = nodes[dep].get("phase"), record.get("phase")
                if dep_phase in PHASES and own_phase in PHASES and PHASES.index(dep_phase) > PHASES.index(own_phase):
                    errors.append(f"{identifier}: prerequisite {dep} is in later phase {dep_phase}")
                if (record.get("readiness") == "Ready" or record.get("status") in {"Ready", "Done"} or record.get("dependency_status") == "Ready") and nodes[dep].get("status") != "Done":
                    errors.append(f"{identifier}: unresolved prerequisite {dep} prevents Ready/Done")
            for field in ("external_handoffs",):
                for url in record.get(field, []):
                    if not _url(url):
                        errors.append(f"{identifier}.{field}: credential-free HTTPS URL required")
            if "external_dependencies" in record:
                errors.append(f"{identifier}: use external_handoffs; external coordination is not a native blocker")
            if record.get("status") == "Done":
                if record.get("acceptance_status") != "Accepted":
                    errors.append(f"{identifier}: Done requires Accepted acceptance status")
                errors.extend(_receipt_errors(record.get("acceptance_receipts"), f"{identifier}.acceptance_receipts"))
                for child in children.get(identifier, []):
                    if (nodes[child].get("status") != "Done" if levels[child] in NATIVE_LEVELS else nodes[child].get("done") is not True):
                        errors.append(f"{identifier}: Done parent has incomplete child {child}")
            elif record.get("acceptance_status") == "Accepted":
                errors.append(f"{identifier}: Accepted requires Done status and accepted delivery receipts")
        else:
            if type(record.get("done")) is not bool:
                errors.append(f"{identifier}.done: boolean required")
            if record.get("done") is True:
                errors.extend(_receipt_errors(record.get("acceptance_receipts"), f"{identifier}.acceptance_receipts"))
                for child in children.get(identifier, []):
                    if nodes[child].get("done") is not True:
                        errors.append(f"{identifier}: completed task has incomplete subtask {child}")
    errors.extend(_cycle_errors(graph))

    package_ids = set(packages)
    def references(rows, label, id_key="id"):
        seen = set()
        if not isinstance(rows, list):
            errors.append(f"{label}: array required")
            return []
        valid = []
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"{label}: object entries required")
                continue
            rid = row.get(id_key)
            if not isinstance(rid, str) or not rid.strip() or rid in seen:
                errors.append(f"{label}: missing or duplicate identity {rid!r}")
            else:
                seen.add(rid)
            refs = row.get("work_packages")
            if not isinstance(refs, list) or not refs or any(not isinstance(x, str) for x in refs):
                errors.append(f"{label}.{rid}: nonempty work_packages references required")
                continue
            if len(refs) != len(set(refs)):
                errors.append(f"{label}.{rid}: duplicate work package reference")
            for ref in refs:
                if ref not in package_ids:
                    errors.append(f"{label}.{rid}: missing work package {ref}")
            valid.append(row)
        return valid

    requirements = references(coverage.get("requirements"), "coverage.requirements")
    covered = Counter(ref for row in requirements for ref in row["work_packages"])
    for identifier in sorted(package_ids):
        if covered[identifier] != 1:
            errors.append(f"coverage: {identifier} requires exactly one primary requirement mapping (found {covered[identifier]})")
    epic_sets = [frozenset(p["id"] for p in e["work_packages"]) for e in epics.values() if isinstance(e.get("work_packages"), list)]
    for row in requirements:
        if frozenset(row["work_packages"]) not in epic_sets:
            errors.append(f"coverage.{row.get('id')}: primary requirement must cover one complete epic")
    domains = references(coverage.get("domains"), "coverage.domains", "domain_id")
    present_domains = {d.get("domain_id") for d in domains}
    for missing in sorted(REQUIRED_DOMAINS - present_domains):
        errors.append(f"coverage: missing ecosystem domain {missing}")
    for domain in domains:
        measurement = domain.get("measurement", {})
        if not isinstance(measurement, dict):
            errors.append(f"coverage.{domain.get('domain_id')}: measurement object required")
            continue
        if domain.get("state") == "Planned" and any(v is not None for v in measurement.values()):
            errors.append(f"coverage.{domain.get('domain_id')}: Planned counts must remain unknown, not invented measurements")
        for key, value in measurement.items():
            if value is not None and (type(value) is not int or value < 0):
                errors.append(f"coverage.{domain.get('domain_id')}.{key}: nonnegative integer or null required")
    consumer_rows = references(coverage.get("consumer_contracts"), "coverage.consumer_contracts")
    for missing in sorted(REQUIRED_CONSUMERS - {c.get("id") for c in consumer_rows}):
        errors.append(f"coverage: missing consumer contract {missing}")

    decision_rows = references(decisions.get("decisions"), "decisions")
    for decision in decision_rows:
        did = decision.get("id")
        if decision.get("status") == "Existing accepted boundary" and not decision.get("references"):
            errors.append(f"{did}: existing accepted boundary requires an upstream reference")
        for phase in decision.get("affected_release_gate", []):
            if phase not in PHASES:
                errors.append(f"{did}: invalid affected release phase {phase!r}")
        if decision.get("status") == "Accepted" or decision.get("accepted_by") or decision.get("actual_approvers"):
            errors.extend(_receipt_errors(decision.get("evidence"), f"{did}.evidence"))
            if decision.get("status") == "Accepted" and not decision.get("accepted_by"):
                errors.append(f"{did}: Accepted decision requires actual accepted_by identities")

    bootstrap = releases.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        errors.append("release.bootstrap: object required")
        bootstrap = {}
    for key, expected in {"synthetic_only": True, "publication_eligible": False, "deployed": False}.items():
        if bootstrap.get(key) is not expected:
            errors.append(f"release.bootstrap.{key}: must remain {expected}; bootstrap is not production")
    if type(bootstrap.get("production_record_count")) is not int or bootstrap["production_record_count"] != 0:
        errors.append("release.bootstrap.production_record_count: must be integer zero")
    phase_rows = releases.get("phases", [])
    assigned, seen_phases = Counter(), set()
    if not isinstance(phase_rows, list):
        errors.append("release.phases: array required")
        phase_rows = []
    for phase in phase_rows:
        if not isinstance(phase, dict):
            errors.append("release.phases: object entries required")
            continue
        name = phase.get("name")
        if name not in PHASES or name in seen_phases:
            errors.append(f"release: invalid or duplicate phase {name!r}")
        seen_phases.add(name)
        refs = phase.get("required_work_packages", [])
        if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
            errors.append(f"release.{name}: work package reference array required")
            continue
        for ref in refs:
            assigned[ref] += 1
            if ref not in packages:
                errors.append(f"release.{name}: missing work package {ref}")
            elif packages[ref].get("phase") != name:
                errors.append(f"release.{name}: {ref} is assigned to {packages[ref].get('phase')}, not this phase")
        if phase.get("state") == "Accepted":
            receipts = [r for r in releases.get("release_evidence", []) if isinstance(r, dict) and r.get("phase") == name]
            errors.extend(_receipt_errors(receipts, f"release.{name}.release_evidence"))
            for ref in refs:
                if ref in packages and packages[ref].get("status") != "Done":
                    errors.append(f"release.{name}: accepted phase has incomplete package {ref}")
    for identifier in sorted(package_ids):
        if assigned[identifier] != 1:
            errors.append(f"release: {identifier} must belong to exactly one phase (found {assigned[identifier]})")
    for receipt in releases.get("release_evidence", []):
        if not isinstance(receipt, dict) or receipt.get("phase") not in seen_phases:
            errors.append("release_evidence: receipt must refer to an exact declared phase")

    if coverage.get("parent_issue") != program.get("parent_research_issue"):
        errors.append("coverage.parent_issue: must match program.parent_research_issue")
    generated = backlog.get("generated_at")
    try:
        if not isinstance(generated, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", generated, re.ASCII):
            raise ValueError
        date.fromisoformat(generated)
    except ValueError:
        errors.append("backlog.generated_at: real YYYY-MM-DD date required")
    errors.extend(_github_identity_errors(bundle))
    return errors


def validate_repository(root):
    """Read four planning files, validate schemas, then cross-file semantics."""
    root = Path(root)
    errors, bundle = [], {}
    for key, filename in FILES.items():
        try:
            bundle[key] = load_json(root / "planning" / filename)
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f"planning/{filename}: {exc}")
    if errors:
        return errors
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        return ["JSON Schema dependency unavailable; run python -m pip install -r requirements-validation.txt"]
    for key, filename in SCHEMAS.items():
        try:
            schema = load_json(root / "schemas" / "planning" / filename)
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            for error in sorted(validator.iter_errors(bundle[key]), key=lambda e: str(list(e.absolute_path))):
                location = ".".join(str(part) for part in error.absolute_path) or "<root>"
                errors.append(f"{FILES[key]}:{location}: {error.message}")
        except (OSError, ValueError, SchemaError) as exc:
            errors.append(f"schemas/planning/{filename}: {exc}")
    if errors:
        return errors
    errors.extend(validate_bundle(bundle))
    project_path = root / "planning" / "project-config.json"
    if project_path.exists():
        try:
            errors.extend(validate_project_config(load_json(project_path), bundle["backlog"]))
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f"planning/project-config.json: {exc}")
    return errors


def validate_project_config(config, backlog):
    """Cross-check intended Project vocabulary; this is not a live API readback."""
    if not isinstance(config, dict) or not isinstance(config.get("fields"), list):
        return ["project-config: object with field definitions required"]
    errors, indexed = [], {}
    for field in config["fields"]:
        if not isinstance(field, dict) or not isinstance(field.get("name"), str):
            errors.append("project-config: every field needs a name")
            continue
        name = field["name"]
        if name in indexed:
            errors.append(f"project-config: duplicate field {name}")
        indexed[name] = field
    required = {"Status": STATUSES, "Priority": PRIORITIES, "Readiness": READINESS,
                "Evidence Confidence": EVIDENCE, "Source Rights Status": RIGHTS, "Dependency Status": DEPENDENCIES,
                "Effort": EFFORT, "Release Phase": PHASES, "Acceptance Status": ACCEPTANCE,
                "Record Type": ("Program", "Epic", "Work Package", "Task"),
                "Workstream": ("Program", *(e["workstream"] for e in backlog["epics"]))}
    for name, options in required.items():
        field = indexed.get(name, {})
        if field.get("type") != "SINGLE_SELECT" or field.get("options") != list(options):
            errors.append(f"project-config.{name}: exact canonical single-select options required")
    if config.get("native_ownership") != "Assignees" or any(name.lower() in {"owner", "owners", "assignee", "assignees"} for name in indexed):
        errors.append("project-config: native Assignees must own work; no invented duplicate ownership field")
    if config.get("repository") != "Pick-Your-AI/pick-your-ai-catalog-pipeline":
        errors.append("project-config.repository: wrong target repository")
    errors.extend(_github_identity_errors(config, "project-config"))
    return errors
