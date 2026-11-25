"""Bounded, offline consistency checking; never an adoption authorizer.

Only fixed repository-owned schemas are loaded at import. check_packet performs
no I/O and accepts explicit bytes, never paths to fetch. Its result describes
untrusted input consistency, not authentic provenance, rights or acceptance.
"""
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker

MAX_DOCUMENT_BYTES = 131072
MAX_ARTIFACT_BYTES = 262144
MAX_TOTAL_BYTES = 2097152
MAX_ARTIFACTS = 32
MAX_DEPTH = 32
MAX_NODES = 10000
MAX_STRING = 8192
CONSUMERS = ("website", "apple", "android")
_PATH = re.compile(r"examples/[a-z0-9-]+\.json", re.ASCII)
_ID = re.compile(r"urn:pya:[a-z0-9][a-z0-9:._-]+", re.ASCII)
_CLAIM_PATH = re.compile(r"[a-z][a-z0-9_.-]+", re.ASCII)
_ROOT = Path(__file__).resolve().parents[2]
_VALIDATORS = {}
for _name in ("consumer-receipt", "release-manifest", "catalog-record"):
    _schema = json.loads((_ROOT / f"schemas/v0.1/{_name}.schema.json").read_bytes())
    Draft202012Validator.check_schema(_schema)
    _VALIDATORS[_name] = Draft202012Validator(_schema, format_checker=FormatChecker())


class PacketError(ValueError):
    """Fixed diagnostic without input-derived content or chained exceptions."""


def _fail():
    raise PacketError("Synthetic packet consistency check failed.")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _constant(_value):
    _fail()


def _load(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        _fail()
    # Scan nesting before parsing, so pathological nesting never reaches the
    # recursive JSON decoder. Quoted braces and escaped quotes do not count.
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                _fail()
        elif byte in (93, 125):
            depth -= 1
    failed = False
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=_constant, parse_float=_constant)
    except (ValueError, UnicodeError, RecursionError):
        failed = True
    if failed:
        _fail()  # Outside the except: no parser context/cause or payload leak.
    nodes = 0
    pending = [value]
    while pending:
        item = pending.pop()
        nodes += 1
        if nodes > MAX_NODES:
            _fail()
        if isinstance(item, str) and (len(item) > MAX_STRING or
                                      any(0xD800 <= ord(c) <= 0xDFFF for c in item)):
            _fail()
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


def _validate(value, name):
    if not _VALIDATORS[name].is_valid(value):
        _fail()
    # The legacy manifest/record schemas use $, which can match before a final
    # LF. Preserve their identifier grammar but require the whole token here.
    # Traverse only structured identifier fields, never arbitrary claim values.
    if name == "release-manifest":
        _identifiers([value["id"], *value["rights_decision_ids"]])
        for approval in value["approvals"]:
            _identifiers([approval["reviewer_ref"], approval["receipt_ref"]])
    elif name == "catalog-record":
        _identifiers([value["id"], *(r["target_id"] for r in value["relationships"])])
        for claim in value["claims"]:
            _identifiers([claim["id"]])
            if not _CLAIM_PATH.fullmatch(claim["path"]):
                _fail()
            if "receipt_ref" in claim["evidence"]:
                _identifiers([claim["evidence"]["receipt_ref"]])
            for source in claim["sources"]:
                _identifiers([source["source_id"], source["material_id"]])


def _identifiers(values):
    if any(not _ID.fullmatch(value) for value in values):
        _fail()


def _entries(entries):
    if not 1 <= len(entries) <= MAX_ARTIFACTS:
        _fail()
    paths, identities = set(), set()
    result = {}
    for entry in entries:
        path, record_id = entry["path"], entry["record_id"]
        if (not _PATH.fullmatch(path) or not _ID.fullmatch(record_id)
                or path in paths or record_id in identities
                or type(entry["revision"]) is not int):
            _fail()
        paths.add(path)
        identities.add(record_id)
        result[path] = entry
    return result


def check_packet(packet_bytes, manifest_bytes, artifacts, *, consumer):
    """Return the declared unresolved/rejected/rehearsal state if consistent.

    artifacts must be an exact plain dict of safe manifest paths to bytes.
    The caller supplies all data explicitly. Matching a caller-supplied hash
    anchor establishes consistency only; it never authenticates that anchor.
    No receiver identity, signature, acceptance or permission is fabricated.
    """
    if type(consumer) is not str or consumer not in CONSUMERS:
        _fail()
    if type(artifacts) is not dict or not 1 <= len(artifacts) <= MAX_ARTIFACTS:
        _fail()
    total = 0
    for path, raw in artifacts.items():
        if (type(path) is not str or not _PATH.fullmatch(path) or
                type(raw) is not bytes or not 0 < len(raw) <= MAX_ARTIFACT_BYTES):
            _fail()
        total += len(raw)
    if total > MAX_TOTAL_BYTES:
        _fail()
    packet = _load(packet_bytes, MAX_DOCUMENT_BYTES)
    manifest = _load(manifest_bytes, MAX_DOCUMENT_BYTES)
    _validate(packet, "consumer-receipt")
    _validate(manifest, "release-manifest")
    anchor = packet["manifest"]
    if (packet["consumer"] != consumer or manifest["synthetic"] is not True or
            not manifest["id"].startswith("urn:pya:synthetic:") or
            type(manifest["revision"]) is not int or
            anchor["id"] != manifest["id"] or
            anchor["revision"] != manifest["revision"] or
            anchor["schema_version"] != manifest["schema_version"] or
            anchor["sha256"] != hashlib.sha256(manifest_bytes).hexdigest()):
        _fail()
    expected = _entries(manifest["artifacts"])
    supplied = _entries(packet["artifacts"])
    if supplied != expected or set(artifacts) != set(expected):
        _fail()
    for path, entry in expected.items():
        raw = artifacts[path]
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            _fail()
        record = _load(raw, MAX_ARTIFACT_BYTES)
        _validate(record, "catalog-record")
        if (record["synthetic"] is not True or
                not record["id"].startswith("urn:pya:synthetic:") or
                record["id"] != entry["record_id"] or
                type(record["revision"]) is not int or
                record["revision"] != entry["revision"]):
            _fail()
    return packet["status"]
