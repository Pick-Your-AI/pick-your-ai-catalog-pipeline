# Untrusted source boundary — initial offline threat model

**Status:** partial implementation for CP-13.02, not a production security
acceptance or proof that a deployed source pipeline is safe.

## Trust boundaries

1. **Outbound acquisition — not implemented:** an adapter must obtain an
   explicit rights and destination decision before *any* request. URL allowlists,
   DNS rebinding, redirect hops, private/link-local/loopback network addresses,
   response timeouts and quotas remain required. This repository's JSON parser
   does not make network requests and cannot authorize requests.
2. **Content decoding — partially implemented:** the offline
   `src.security.input_controls.parse_untrusted_json` entrypoint rejects
   oversized UTF-8 JSON, duplicate keys, nonfinite numbers, excess nesting,
   excess node counts and unsupported or invalid numeric representations.
   Exact JSON decimals remain `Decimal` rather than silently rounded floats.
3. **Observation and claims — not implemented:** parsed fields are untrusted
   observations, not accepted assertions. Mapping, provenance, explicit unknowns,
   source-use decisions, deduplication and review must independently validate them.
4. **Presentation and enrichment — not implemented:** Markdown, HTML, XML,
   templating, rich media and model prompts require isolated renderers or
   text-only display. Source strings may contain adversarial instructions and
   must not acquire tool authority or access to credentials.
5. **Archives and storage — not implemented:** archive expansion, decompression
   ratios, path traversal, symlinks, storage permissions, durable deletion and
   retention limits need their own defensive implementation and tests.
6. **Publication — not implemented:** parser success is not a signature,
   provenance receipt, rights permission, editorial approval or consumer
   acceptance. A parsed record must never bypass quarantine or release gates.

## Bounds and guarantees of the offline JSON primitive

Defaults: 1 MiB UTF-8 input, nesting depth 32, 10,000 value nodes, 64 integer
digits, 64 decimal significant digits and decimal exponent magnitude 308.
They are resource ceilings, not a claim that they satisfy every future source
contract. The implementation performs no I/O, process execution, network
access, code evaluation, archive extraction, or source-rights decisions.

The caller must supply additional trusted schema validation and contextual
policy checks. Invalid inputs raise `UnsafeJSONError` without logging raw
source content. Duplicate keys are rejected even when both values appear
identical. String payloads remain untrusted data, including text that resembles
instructions.

## Evidence and remaining gates

Run `python -m unittest discover -s tests -v` under the repo's Python 3.12
validation environment. The adversarial tests are synthetic only; they exercise
JSON parsing, not actual SSRF mitigation, archive handling, browser rendering,
sandbox escape, model prompt injection, hosted resilience or security review.

Before CP-13.02 can close, implement and independently assess outbound URL/DNS/
redirect controls, parser isolation and budgets for non-JSON formats, hostile
markup, decompression/archives, source-to-agent injection and cross-stage rights
enforcement. Record concrete negative tests and approved ownership. No production
publication or live source testing is authorized by this document.
