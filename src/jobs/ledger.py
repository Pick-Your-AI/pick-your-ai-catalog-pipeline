"""Bounded offline SQLite rehearsal; stores identities/digests, never source bodies.

No transport, publication, real rights authority, or production storage guarantee.
Caller-supplied current policy is a synthetic test input, not an authority lookup.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
import sqlite3

from src.policy.acquisition import AcquisitionError, preflight


class JobError(ValueError):
    """Fixed admission/state diagnostic without reflected input."""


def _text(value, pattern, limit=256):
    if type(value) is not str or len(value) > limit or re.fullmatch(pattern, value) is None:
        raise JobError("invalid_value")


def _identity(value):
    _text(value, r"urn:pya:synthetic:[a-z0-9][a-z0-9:._-]*")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("ascii")).hexdigest()


def _capture(value, error):
    """Detach bounded built-in primitives before semantic checks or SQLite waits.

    Never deepcopy/serialize caller objects. Limit traversal itself, including
    containers that grow during capture; validate only the resulting private tree.
    """
    remaining = 256

    def take(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 4:
            raise JobError(error)
        kind = type(item)
        if item is None or kind is bool:
            return item
        if kind is str and len(item) <= 256:
            return item
        if kind is int and -1_000_000 <= item <= 1_000_000:
            return item
        if kind not in (dict, list) or len(item) > 32:
            raise JobError(error)
        result = {} if kind is dict else []
        for index, entry in enumerate(item.items() if kind is dict else item):
            if index >= 32:
                raise JobError(error)
            if kind is dict:
                key, child = entry
                if type(key) is not str or len(key) > 256:
                    raise JobError(error)
                result[key] = take(child, depth + 1)
            else:
                result.append(take(entry, depth + 1))
        return result

    try:
        return take(value)
    except RuntimeError:  # A concurrently resized dict is invalid admission.
        pass
    raise JobError(error)


def _instant(now):
    _text(now, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,6})?Z", 27)
    try:
        delta = datetime.fromisoformat(now[:-1] + "+00:00") - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    except ValueError:
        pass
    raise JobError("invalid_time")


def _policy(request, decision, now):
    try:
        return preflight(request, decision, now=now)
    except AcquisitionError:
        pass
    raise JobError("invalid_policy_envelope")


RETRYABLE = frozenset({"timeout", "unavailable", "rate_limited"})
PERMANENT = frozenset({"parse_failed", "validation_failed"})

_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), clock INTEGER, turn INTEGER);
    INSERT OR IGNORE INTO meta VALUES(1, -62135596800000000, 0);
    CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, budget INTEGER, used INTEGER, until_at INTEGER, served INTEGER);
    CREATE TABLE IF NOT EXISTS decisions (id TEXT, revision INTEGER, digest TEXT, used INTEGER, PRIMARY KEY(id, revision));
    CREATE TABLE IF NOT EXISTS jobs (
        seq INTEGER PRIMARY KEY, id TEXT UNIQUE, run_id TEXT, source_id TEXT REFERENCES sources(id),
        request_id TEXT, request_digest TEXT, decision_digest TEXT, parser_version TEXT,
        state TEXT, attempts INTEGER, checkpoint TEXT, completion_digest TEXT,
        UNIQUE(run_id, request_id));
    CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, logical_id TEXT, digest TEXT);
    CREATE TABLE IF NOT EXISTS job_observations (job TEXT REFERENCES jobs(id), observation TEXT REFERENCES observations(id), PRIMARY KEY(job, observation));
    CREATE TABLE IF NOT EXISTS receipts (seq INTEGER PRIMARY KEY, job TEXT REFERENCES jobs(id), state TEXT, reason TEXT, attempt INTEGER, at INTEGER, UNIQUE(job, state, reason, attempt));
"""


class JobLedger:
    """Single-machine test proposal: at most 100 jobs, 8 attempts/job, 16 sources.

    An attempt is one atomic *simulated* result admission, not a network lease.
    Source budgets are immutable lifetime counters, not an inferred rate window.
    """

    @staticmethod
    def _budgets(source_budgets):
        source_budgets = _capture(source_budgets, "invalid_budgets")
        if type(source_budgets) is not dict or not 1 <= len(source_budgets) <= 16:
            raise JobError("invalid_budgets")
        for source, budget in source_budgets.items():
            _identity(source)
            if type(budget) is not int or not 1 <= budget <= 100:
                raise JobError("invalid_budgets")
        return source_budgets

    def __init__(self, path, source_budgets):
        source_budgets = self._budgets(source_budgets)
        self._db = sqlite3.connect(path, timeout=1, isolation_level=None)
        try:
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript(_SCHEMA_SQL)
            with self._transaction():
                existing = {r["id"]: r["budget"] for r in self._db.execute("SELECT * FROM sources")}
                if existing and existing != source_budgets:
                    raise JobError("budget_configuration_changed")
                for source, budget in source_budgets.items():
                    self._db.execute("INSERT OR IGNORE INTO sources VALUES(?, ?, 0, -62135596800000000, 0)", (source, budget))
        except BaseException:
            self.close()
            raise

    @classmethod
    def open_existing(cls, path, source_budgets):
        """Verify an existing temporary ledger in a read transaction; never initialize."""
        budgets = cls._budgets(source_budgets)
        instance = cls.__new__(cls)
        uri = Path(path).absolute().as_uri() + "?mode=rw"
        instance._db = None
        try:
            instance._db = sqlite3.connect(uri, uri=True, timeout=1, isolation_level=None)
            instance._db.row_factory = sqlite3.Row
            instance._db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 8192)
            instance._db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            instance._db.execute("PRAGMA trusted_schema=OFF")
            instance._db.execute("PRAGMA foreign_keys=ON")
            instance._db.execute("PRAGMA synchronous=FULL")
            with instance._transaction(write=False):
                instance._verify_accounting(budgets)
            return instance
        except sqlite3.Error:
            if instance._db is not None:
                instance.close()
        except BaseException:
            if instance._db is not None:
                instance.close()
            raise
        raise JobError("corrupt_ledger") from None

    def _verify_accounting(self, budgets):
        def require(value):
            if not value:
                raise JobError("corrupt_ledger")

        def integer(value, low, high):
            return type(value) is int and low <= value <= high

        # The initializer and verifier share the exact table definitions. Only
        # insignificant whitespace differs in fixtures created by older code.
        tables = {sql.split()[5]: " ".join(sql.replace("IF NOT EXISTS ", "", 1).split())
                  for sql in _SCHEMA_SQL.split(";") if sql.strip().startswith("CREATE TABLE")}
        indexes = {f"sqlite_autoindex_{name}_{number}" for name, count in (
            ("sources", 1), ("decisions", 1), ("jobs", 2), ("observations", 1),
            ("job_observations", 1), ("receipts", 1)) for number in range(1, count + 1)}
        placeholders = ",".join("?" for _ in tables)
        schema = self._db.execute(
            f"SELECT type,name,sql FROM sqlite_schema WHERE tbl_name IN ({placeholders}) LIMIT 32",
            tuple(tables)).fetchall()
        require(len(schema) == len(tables) + len(indexes))
        for row in schema:
            require((row["type"] == "table" and row["name"] in tables
                     and type(row["sql"]) is str and " ".join(row["sql"].split()) == tables[row["name"]])
                    or (row["type"] == "index" and row["name"] in indexes and row["sql"] is None))
        require(self._db.execute("PRAGMA journal_mode").fetchone()[0] == "delete")
        require(self._db.execute("PRAGMA quick_check(1)").fetchone()[0] == "ok")
        rows = self._db.execute("SELECT id, clock, turn FROM meta LIMIT 2").fetchall()
        require(len(rows) == 1 and rows[0]["id"] == 1)
        clock, turn = rows[0]["clock"], rows[0]["turn"]
        origin, end = -62135596800000000, 253402300799999999
        require(integer(clock, origin, end) and integer(turn, 0, sum(budgets.values())))
        require(self._db.execute("PRAGMA foreign_key_check").fetchone() is None)
        sources = self._db.execute("SELECT * FROM sources LIMIT 17").fetchall()
        require(len(sources) == len(budgets) and {s["id"]: s["budget"] for s in sources} == budgets)
        by_source, by_decision = Counter(), Counter()
        jobs = self._db.execute("SELECT * FROM jobs ORDER BY seq LIMIT 101").fetchall()
        require(len(jobs) <= 100)
        for job in jobs:
            require(integer(job["seq"], 1, 100) and integer(job["attempts"], 0, 8)
                    and job["source_id"] in budgets and job["state"] in ("ready", "retry", "done", "dead", "cancelled"))
            for field in ("id", "request_digest", "decision_digest"):
                _text(job[field], r"[a-f0-9]{64}", 64)
            for field in ("run_id", "request_id"):
                _identity(job[field])
            _text(job["parser_version"], r"[a-z0-9][a-z0-9._-]*", 80)
            require(job["id"] == _digest([job["run_id"], job["request_digest"], job["parser_version"]]))
            if job["state"] == "ready":
                require(job["attempts"] == 0)
            if job["state"] == "retry":
                require(1 <= job["attempts"] < 8)
            observed = self._db.execute("""SELECT o.* FROM observations o JOIN job_observations j
                ON o.id=j.observation WHERE j.job=? ORDER BY o.logical_id LIMIT 33""", (job["id"],)).fetchall()
            require(len(observed) <= 32)
            logical_ids = set()
            for observation in observed:
                _identity(observation["logical_id"])
                _text(observation["digest"], r"[a-f0-9]{64}", 64)
                require(observation["logical_id"] not in logical_ids)
                logical_ids.add(observation["logical_id"])
                require(observation["id"] == _digest([job["source_id"], job["request_digest"],
                                                       job["parser_version"], observation["logical_id"]]))
            if job["state"] == "done":
                require(job["attempts"] > 0)
                if job["checkpoint"] is not None:
                    _identity(job["checkpoint"])
                content = [{"id": item["logical_id"], "digest": item["digest"]} for item in observed]
                require(job["completion_digest"] == _digest([content, job["checkpoint"]]))
            else:
                require(not observed and job["completion_digest"] is None and job["checkpoint"] is None)
            by_source[job["source_id"]] += job["attempts"]
            if job["attempts"]:
                by_decision[job["decision_digest"]] += job["attempts"]
        require(sum(by_source.values()) == turn)
        served = set()
        for source in sources:
            used, last = source["used"], source["served"]
            require(integer(source["budget"], 1, 100) and integer(used, 0, source["budget"])
                    and used == by_source[source["id"]] and integer(last, used, turn)
                    and integer(source["until_at"], origin, clock + 3600000000))
            if used:
                require(last not in served)
                served.add(last)
            else:
                require(last == 0 and source["until_at"] == origin)
        require(max(served, default=0) == turn)
        decisions = self._db.execute("SELECT * FROM decisions LIMIT 101").fetchall()
        require(len(decisions) == len(by_decision))
        for decision in decisions:
            _identity(decision["id"])
            digest = decision["digest"]
            require(integer(decision["revision"], 1, 1000000) and integer(decision["used"], 1, 100)
                    and decision["used"] == by_decision.pop(digest, None))
        require(not by_decision)
        require(self._db.execute("""SELECT 1 FROM job_observations WHERE
            typeof(job)<>'text' OR typeof(observation)<>'text' LIMIT 1""").fetchone() is None)
        require(self._db.execute("""SELECT 1 FROM observations o LEFT JOIN job_observations j
            ON o.id=j.observation WHERE j.job IS NULL LIMIT 1""").fetchone() is None)
        # Each charged attempt records an outcome in the same transaction.
        # Other (uncharged) terminal/refusal receipts can share its attempt count.
        admission_refusals = {"missing_decision", "scope_mismatch", "field_mismatch",
                              "permission_not_unconditional", "decision_inactive"}
        refusals = admission_refusals | {"invalid_policy_envelope", "request_changed", "decision_changed",
                                         "decision_binding_conflict"}
        charged_pairs = {("done", "accepted")} | {("retry", reason) for reason in RETRYABLE} | {
            ("dead", reason) for reason in PERMANENT | {"attempts_exhausted", "observation_conflict"}}
        allowed = {"ready": {"admitted"}, "retry": RETRYABLE,
                   "done": {"accepted", "terminal"}, "cancelled": {"operator_cancelled", "terminal"},
                   "refused": refusals | {"completion_conflict"},
                   "dead": refusals | PERMANENT | {"attempts_exhausted", "observation_conflict", "terminal",
                                                   "decision_revision_conflict", "quota_exhausted"}}
        job_map = {job["id"]: job for job in jobs}
        charged_count, latest, fairness, effective, last_retry = Counter(), {}, {}, {}, {}
        retry_ceiling = {}
        receipts = self._db.execute("SELECT * FROM receipts ORDER BY seq LIMIT 10001").fetchall()
        require(len(receipts) <= 10000)
        last_time, last_seq, charge_turn = origin, 0, 0
        for receipt in receipts:
            job = job_map.get(receipt["job"])
            state, reason, attempt = receipt["state"], receipt["reason"], receipt["attempt"]
            require(job is not None and integer(receipt["seq"], last_seq + 1, 10000)
                    and integer(receipt["at"], last_time, clock) and integer(attempt, 0, job["attempts"])
                    and state in allowed and reason in allowed[state])
            last_time, last_seq = receipt["at"], receipt["seq"]
            require((state != "ready" or attempt == 0) and (state != "refused" or job["state"] == "done"))
            pair, previous = (state, reason), effective.get(job["id"])
            if previous is None:
                require(attempt == 0 and (pair == ("ready", "admitted")
                        or (state == "dead" and reason in admission_refusals)))
                effective[job["id"]] = state
            elif previous in ("ready", "retry"):
                require(pair in charged_pairs or (attempt == charged_count[job["id"]] and (
                    pair == ("cancelled", "operator_cancelled") or (state == "dead" and
                    reason in refusals | {"quota_exhausted", "decision_revision_conflict"}))))
                effective[job["id"]] = state
            elif previous == "done":
                require(attempt == charged_count[job["id"]]
                        and (state == "refused" or pair == ("done", "terminal")))
            else:
                require(pair == (previous, "terminal") and attempt == charged_count[job["id"]])
            if pair in charged_pairs:
                require(attempt == charged_count[job["id"]] + 1)
                require((state != "retry" or attempt < 8) and (reason != "attempts_exhausted" or attempt == 8))
                previous_retry = last_retry.get(job["source_id"])
                if previous_retry is not None:
                    require(receipt["at"] >= previous_retry + 1000000)
                    retry_ceiling[job["source_id"]] = min(retry_ceiling[job["source_id"]], receipt["at"])
                charged_count[job["id"]] += 1
                charge_turn += 1
                fairness[job["source_id"]] = charge_turn
                if state == "retry" or reason == "attempts_exhausted":
                    last_retry[job["source_id"]] = receipt["at"]
                    retry_ceiling[job["source_id"]] = receipt["at"] + 3600000000
            latest[job["id"]] = receipt
        require(charge_turn == turn)
        for source in sources:
            require(source["served"] == fairness.get(source["id"], 0))
            retry_at = last_retry.get(source["id"])
            require(source["until_at"] == origin if retry_at is None else
                    integer(source["until_at"], retry_at + 1000000, retry_ceiling[source["id"]]))
        for job in jobs:
            last = latest.get(job["id"])
            require(last is not None and last["attempt"] == job["attempts"]
                    and effective[job["id"]] == job["state"]
                    and charged_count[job["id"]] == job["attempts"]
                    and (last["state"] == job["state"] or (job["state"] == "done" and last["state"] == "refused")))

    def lookup_run(self, run_id, request_id):
        """Look up existing work by ledger admission identity without creating it."""
        _identity(run_id)
        _identity(request_id)
        row = self._db.execute("SELECT id FROM jobs WHERE run_id=? AND request_id=?",
                               (run_id, request_id)).fetchone()
        if row:
            _text(row[0], r"[a-f0-9]{64}", 64)
        return row[0] if row else None

    def close(self):
        self._db.close()

    @contextmanager
    def _transaction(self, *, write=True):
        self._db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def _clock(self, now):
        instant = _instant(now)
        if instant < self._db.execute("SELECT clock FROM meta").fetchone()[0]:
            raise JobError("clock_regressed")
        return instant

    def _job(self, job_id):
        _text(job_id, r"[a-f0-9]{64}", 64)
        row = self._db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise JobError("unknown_job")
        return row

    def _receipt(self, job, state, reason):
        self._db.execute("INSERT OR IGNORE INTO receipts(job,state,reason,attempt,at) VALUES(?,?,?,?,(SELECT clock FROM meta))",
                         (job["id"], state, reason, job["attempts"]))
        return {"synthetic": True, "evidence_level": "synthetic_unverified", "state": state,
                "reason": reason, "rights_cleared": False, "publication_eligible": False}

    def _finish(self, job, state, reason):
        self._db.execute("UPDATE jobs SET state=? WHERE id=?", (state, job["id"]))
        return self._receipt(job, state, reason)

    def admit(self, run_id, request, decision, parser_version, *, now):
        _identity(run_id)
        _text(parser_version, r"[a-z0-9][a-z0-9._-]*", 80)
        request = _capture(request, "invalid_policy_envelope")
        decision = _capture(decision, "invalid_policy_envelope")
        result = _policy(request, decision, now)
        request_digest, decision_digest = _digest(request), _digest(decision)
        job_id = _digest([run_id, request_digest, parser_version])
        with self._transaction():
            instant = self._clock(now)
            old = self._db.execute("SELECT * FROM jobs WHERE run_id=? AND request_id=?", (run_id, request["id"])).fetchone()
            if old:
                if old["id"] != job_id or old["decision_digest"] != decision_digest:
                    raise JobError("identity_conflict")
                self._db.execute("UPDATE meta SET clock=?", (instant,))
                if result["status"] != "simulated_permit":
                    if old["state"] in {"ready", "retry"}:
                        self._finish(old, "dead", result["reason"])
                    elif old["state"] == "done":
                        self._receipt(old, "refused", result["reason"])
                return job_id
            if self._db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] >= 100:
                raise JobError("job_capacity")
            if self._db.execute("SELECT 1 FROM sources WHERE id=?", (request["source_id"],)).fetchone() is None:
                raise JobError("undeclared_source")
            self._db.execute("INSERT INTO jobs(id,run_id,source_id,request_id,request_digest,decision_digest,parser_version,state,attempts) VALUES(?,?,?,?,?,?,?,'ready',0)",
                             (job_id, run_id, request["source_id"], request["id"], request_digest, decision_digest, parser_version))
            self._db.execute("UPDATE meta SET clock=?", (instant,))
            job = self._job(job_id)
            if result["status"] != "simulated_permit":
                self._finish(job, "dead", result["reason"])
            else:
                self._receipt(job, "ready", "admitted")
        return job_id

    def _next(self, instant):
        row = self._db.execute("""SELECT j.id FROM jobs j JOIN sources s ON j.source_id=s.id
            WHERE j.state IN ('ready','retry') AND s.until_at<=?
            ORDER BY s.served, j.seq LIMIT 1""", (instant,)).fetchone()
        return row[0] if row else None

    def next_ready(self, *, now):
        return self._next(self._clock(now))

    def _rights(self, job, request, decision, now):
        try:
            result = _policy(request, decision, now)
        except JobError:
            return "invalid_policy_envelope"
        if _digest(request) != job["request_digest"]:
            return "request_changed"
        if result["status"] != "simulated_permit":
            return result["reason"]
        if _digest(decision) != job["decision_digest"]:
            return "decision_changed"
        # The supplied, digest-bound decision now establishes the meaning of the
        # retained accounting key. A changed key must not start a fresh allowance.
        retained = self._db.execute("SELECT id,revision FROM decisions WHERE digest=? LIMIT 2",
                                    (job["decision_digest"],)).fetchall()
        if (len(retained) > 1 or (retained and tuple(retained[0]) != (decision["id"], decision["revision"]))
                or (not retained and self._db.execute(
                    "SELECT 1 FROM jobs WHERE decision_digest=? AND attempts>0 LIMIT 1",
                    (job["decision_digest"],)).fetchone() is not None)):
            return "decision_binding_conflict"
        return None

    def attempt(self, job_id, request, decision, *, now, outcome="accepted",
                observations=None, checkpoint=None, retry_after=0):
        """Admit a bounded synthetic result; no bytes or arbitrary failure text.

        Accepted metadata descriptors have exactly {id, digest}; digest is not
        source evidence or rights. Invalid API shapes raise without consuming work.
        """
        if type(outcome) is not str or outcome not in RETRYABLE | PERMANENT | {"accepted"}:
            raise JobError("invalid_outcome")
        if type(retry_after) is not int or not 0 <= retry_after <= 3600 or (outcome not in RETRYABLE and retry_after):
            raise JobError("invalid_retry_after")
        observations = _capture([] if observations is None else observations, "invalid_observations")
        if type(observations) is not list or len(observations) > 32:
            raise JobError("invalid_observations")
        seen = set()
        for observation in observations:
            if type(observation) is not dict or any(type(key) is not str for key in observation) or set(observation) != {"id", "digest"}:
                raise JobError("invalid_observations")
            _identity(observation["id"])
            _text(observation["digest"], r"[a-f0-9]{64}", 64)
            if observation["id"] in seen:
                raise JobError("duplicate_observation")
            seen.add(observation["id"])
        if checkpoint is not None:
            _identity(checkpoint)
        if outcome != "accepted" and (observations or checkpoint is not None):
            raise JobError("failure_has_result")
        completion = _digest([sorted(observations, key=lambda item: item["id"]), checkpoint])
        try:
            request = _capture(request, "invalid_policy_envelope")
            decision = _capture(decision, "invalid_policy_envelope")
        except JobError:
            # Preserve durable policy refusal even for unsupported/cyclic inputs.
            request = decision = None
        with self._transaction():
            instant = self._clock(now)
            job = self._job(job_id)
            self._db.execute("UPDATE meta SET clock=?", (instant,))
            if job["state"] in {"dead", "cancelled"}:
                return self._receipt(job, job["state"], "terminal")
            refusal = self._rights(job, request, decision, now)
            if refusal:
                # Completed history is retained; replay never gains permission.
                if job["state"] == "done":
                    return self._receipt(job, "refused", refusal)
                return self._finish(job, "dead", refusal)
            if job["state"] == "done":
                if outcome != "accepted" or completion != job["completion_digest"]:
                    return self._receipt(job, "refused", "completion_conflict")
                return self._receipt(job, "done", "accepted")
            if self._next(instant) != job_id:
                raise JobError("not_scheduled")
            source = self._db.execute("SELECT * FROM sources WHERE id=?", (job["source_id"],)).fetchone()
            prior = self._db.execute("SELECT * FROM decisions WHERE id=? AND revision=?", (decision["id"], decision["revision"])).fetchone()
            if prior and prior["digest"] != job["decision_digest"]:
                return self._finish(job, "dead", "decision_revision_conflict")
            if source["used"] >= source["budget"] or (prior and prior["used"] >= decision["max_simulated_calls"]):
                return self._finish(job, "dead", "quota_exhausted")
            self._db.execute("UPDATE meta SET turn=turn+1")
            self._db.execute("UPDATE sources SET used=used+1, served=(SELECT turn FROM meta) WHERE id=?", (job["source_id"],))
            self._db.execute("INSERT INTO decisions VALUES(?,?,?,1) ON CONFLICT(id,revision) DO UPDATE SET used=used+1", (decision["id"], decision["revision"], job["decision_digest"]))
            self._db.execute("UPDATE jobs SET attempts=attempts+1 WHERE id=?", (job_id,))
            job = self._job(job_id)
            if outcome in RETRYABLE:
                self._db.execute("UPDATE sources SET until_at=? WHERE id=?", (instant + max(1, retry_after) * 1000000, job["source_id"]))
                return self._finish(job, "dead" if job["attempts"] >= 8 else "retry", "attempts_exhausted" if job["attempts"] >= 8 else outcome)
            if outcome in PERMANENT:
                return self._finish(job, "dead", outcome)
            bound = [(_digest([job["source_id"], job["request_digest"], job["parser_version"], item["id"]]), item) for item in observations]
            for identity, item in bound:
                old = self._db.execute("SELECT digest FROM observations WHERE id=?", (identity,)).fetchone()
                if old and old[0] != item["digest"]:
                    return self._finish(job, "dead", "observation_conflict")
            for identity, item in bound:
                self._db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?)", (identity, item["id"], item["digest"]))
                self._db.execute("INSERT INTO job_observations VALUES(?,?)", (job_id, identity))
            self._db.execute("UPDATE jobs SET checkpoint=?, completion_digest=? WHERE id=?", (checkpoint, completion, job_id))
            return self._finish(job, "done", "accepted")

    def cancel(self, job_id, *, now):
        with self._transaction():
            instant = self._clock(now)
            job = self._job(job_id)
            self._db.execute("UPDATE meta SET clock=?", (instant,))
            if job["state"] in {"done", "dead", "cancelled"}:
                return self._receipt(job, job["state"], "terminal")
            return self._finish(job, "cancelled", "operator_cancelled")

    def snapshot(self, job_id):
        # A single read view keeps metadata coherent across concurrent commits.
        with self._transaction(write=False):
            job = self._job(job_id)
            keys = ("id", "run_id", "source_id", "request_id", "request_digest", "decision_digest", "parser_version", "state", "attempts", "checkpoint")
            return {"schema_version": "synthetic-ingestion-run-0.1", "synthetic": True,
                    "evidence_level": "synthetic_unverified", "rights_cleared": False,
                    "publication_eligible": False, **{key: job[key] for key in keys},
                    "observations": [dict(row) for row in self._db.execute("SELECT o.* FROM observations o JOIN job_observations j ON o.id=j.observation WHERE j.job=? ORDER BY o.id", (job_id,))],
                    "receipts": [dict(row) for row in self._db.execute("SELECT state,reason,attempt,at FROM receipts WHERE job=? ORDER BY seq", (job_id,))]}
