"""Offline, synthetic-only quarantine dispositions; never publication authority.

All five independent gate results are required at each attempt. The gate
implementation and external evidence custody are deliberately not supplied.
"""
from dataclasses import dataclass
import re

GATES = ("schema", "identity", "evidence", "rights", "policy")
CAUSES = {
    "malformed": ("schema", "correct_and_retry"),
    "identity_ambiguous": ("identity", "resolve_identity"),
    "evidence_insufficient": ("evidence", "supply_evidence"),
    "rights_unknown": ("rights", "request_rights_review"),
    "policy_denied": ("policy", "request_policy_review"),
}
MAX_ATTEMPTS = 32
MAX_BATCH = 128
_SYNTHETIC = re.compile(r"urn:pya:synthetic:[a-z0-9][a-z0-9:._-]*\Z")


class QuarantineError(ValueError):
    """Malformed or untrustworthy local attempt metadata."""


@dataclass(frozen=True, slots=True)
class GateFinding:
    gate: str
    status: str  # pass, reject or unknown
    evaluation_id: str
    cause: str | None = None


@dataclass(frozen=True, slots=True)
class Attempt:
    candidate_id: str
    revision: int
    number: int
    state: str  # quarantined or needs_independent_review; never released
    causes: tuple[str, ...]
    next_actions: tuple[str, ...]
    findings: tuple[GateFinding, ...]


def _synthetic(value):
    return type(value) is str and len(value) <= 256 and _SYNTHETIC.fullmatch(value) is not None


def _normalize(findings):
    if type(findings) is not tuple or len(findings) != len(GATES):
        raise QuarantineError("A fresh result from all five gates is required")
    by_gate = {}
    for finding in findings:
        if type(finding) is not GateFinding:
            raise QuarantineError("Expected an exact gate finding")
        try:
            gate, status, evaluation_id, cause = (
                finding.gate, finding.status, finding.evaluation_id, finding.cause)
        except AttributeError as error:
            raise QuarantineError("Incomplete gate finding") from error
        # Validate exact primitive types before equality, membership or hashing:
        # even a str subclass may override those operations or be unhashable.
        if (type(gate) is not str or type(status) is not str
                or (cause is not None and type(cause) is not str)):
            raise QuarantineError("Gate fields must use exact scalar types")
        if not _synthetic(evaluation_id):
            raise QuarantineError("Invalid synthetic evaluation identity")
        if gate not in GATES or gate in by_gate:
            raise QuarantineError("Unknown or duplicate gate")
        if status not in ("pass", "reject", "unknown"):
            raise QuarantineError("Invalid gate result or synthetic evaluation identity")
        if status == "pass":
            if cause is not None:
                raise QuarantineError("Passing gate cannot supply a failure cause")
        elif cause not in CAUSES or CAUSES[cause][0] != gate:
            raise QuarantineError("Failed/unknown gate requires matching cause")
        by_gate[gate] = finding
    ordered = tuple(by_gate[g] for g in GATES)
    if len({f.evaluation_id for f in ordered}) != len(GATES):
        raise QuarantineError("Gate evaluations must have distinct identities")
    return ordered


def _derived(findings):
    causes = tuple(f.cause for f in findings if f.cause is not None)
    actions = tuple(dict.fromkeys(CAUSES[c][1] for c in causes))
    return ("quarantined" if causes else "needs_independent_review", causes, actions)


def _validate_attempt(entry):
    """Check one stored attempt's bounded structure and derived consistency.

    This cannot authenticate a history, prove a gate ran, or establish that a
    caller supplied the complete prior history. Cross-attempt checks belong to
    append_attempt; even a valid standalone document is not a trusted receipt.
    """
    if type(entry) is not Attempt:
        raise QuarantineError("Expected an exact attempt")
    try:
        candidate_id, revision, number, state, causes, actions, findings = (
            entry.candidate_id, entry.revision, entry.number, entry.state,
            entry.causes, entry.next_actions, entry.findings)
    except AttributeError as error:
        raise QuarantineError("Incomplete attempt") from error
    if not _synthetic(candidate_id) or type(revision) is not int or revision < 1:
        raise QuarantineError("Candidate and positive revision must be synthetic and exact")
    if type(number) is not int or not 1 <= number <= MAX_ATTEMPTS:
        raise QuarantineError("Attempt number is outside the supported range")
    if (type(state) is not str
            or type(causes) is not tuple or len(causes) > len(GATES)
            or type(actions) is not tuple or len(actions) > len(GATES)):
        raise QuarantineError("Attempt metadata must use exact bounded types")
    if any(type(value) is not str for value in causes + actions):
        raise QuarantineError("Attempt causes and actions must use exact strings")
    normalized = _normalize(findings)
    if tuple(f.gate for f in findings) != GATES:
        raise QuarantineError("Stored findings must use canonical gate order")
    if (state, causes, actions) != _derived(normalized):
        raise QuarantineError("Inconsistent prior attempt metadata")


def append_attempt(history, *, candidate_id, revision, findings):
    """Return a new immutable history; require new revision and all fresh gates.

    Data-only synthetic harness. An evaluation ID is not a signed receipt, and
    needs_independent_review is not permission to publish or release.
    """
    if not _synthetic(candidate_id) or type(revision) is not int or revision < 1:
        raise QuarantineError("Candidate and positive revision must be synthetic and exact")
    if type(history) is not tuple or len(history) >= MAX_ATTEMPTS:
        raise QuarantineError("History must be a bounded immutable tuple")
    seen = set()
    prior_revision = 0
    for number, entry in enumerate(history, 1):
        _validate_attempt(entry)
        if entry.candidate_id != candidate_id:
            raise QuarantineError("Foreign or malformed prior attempt")
        if entry.number != number or entry.revision <= prior_revision:
            raise QuarantineError("Nonmonotonic prior attempt history")
        for finding in entry.findings:
            if finding.evaluation_id in seen:
                raise QuarantineError("Reused evaluation identity in prior history")
            seen.add(finding.evaluation_id)
        prior_revision = entry.revision
    if revision <= prior_revision:
        raise QuarantineError("Correction must use a strictly newer revision")
    normalized = _normalize(findings)
    if any(f.evaluation_id in seen for f in normalized):
        raise QuarantineError("Re-entry must supply new results from every gate")
    state, causes, actions = _derived(normalized)
    return history + (Attempt(candidate_id, revision, len(history) + 1,
                              state, causes, actions, normalized),)


def as_document(entry):
    """Machine-readable disposition, never an eligibility or rights receipt."""
    _validate_attempt(entry)
    return {
        "synthetic": True, "candidate_id": entry.candidate_id,
        "revision": entry.revision, "attempt": entry.number,
        "state": entry.state, "causes": list(entry.causes),
        "next_actions": list(entry.next_actions),
        "evaluations": [dict(gate=f.gate, status=f.status,
                             evaluation_id=f.evaluation_id,
                             **({"cause": f.cause} if f.cause else {}))
                        for f in entry.findings],
    }


def evaluate_batch(items):
    """Return per-item (candidate_id, history, error), never publication output.

    Malformed entries are isolated so one bad packet cannot mask diagnostics for
    independent candidates. Duplicate candidate IDs fail closed in the batch.
    """
    if type(items) is not tuple or len(items) > MAX_BATCH:
        raise QuarantineError("Expected a bounded tuple of candidate inputs")
    used = set()
    results = []
    for item in items:
        if type(item) is not tuple or len(item) != 4:
            results.append((None, None, "malformed_batch_item"))
            continue
        candidate_id, revision, history, findings = item
        if not _synthetic(candidate_id):
            results.append((None, None, "invalid_candidate_id"))
        elif candidate_id in used:
            results.append((candidate_id, None, "duplicate_candidate_id"))
        else:
            used.add(candidate_id)
            try:
                results.append((candidate_id, append_attempt(
                    history, candidate_id=candidate_id, revision=revision,
                    findings=findings), None))
            except QuarantineError:
                results.append((candidate_id, None, "invalid_attempt"))
    return tuple(results)
