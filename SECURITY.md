# Security policy

## Current scope

This repository begins as a planning, schema and validation bootstrap. It does not establish a deployed service, an operational security response team, or a supported production release. Runtime support periods and response objectives require an accepted operational release decision.

## Report a vulnerability

When this repository is available on GitHub and private vulnerability reporting is enabled, use **Security → Report a vulnerability**. If that option is unavailable, contact an organization owner through GitHub and request a private reporting route. Do not publish exploit details, credentials or personal data in a public issue while arranging that route. This document does not assert that private reporting is already enabled.

Include a concise description, affected revision and component, reproduction steps using sanitized data, potential impact, and relevant logs with secrets removed. Do not access or extract third-party information to demonstrate impact.

Relevant reports include exposed credentials or personal data, unsafe ingestion URLs, parser or archive attacks, authorization failures, source-content instruction injection, provenance tampering, review-gate bypass, publication of ineligible material, and compromised release artifacts or dependencies.

## Contributor requirements

- Never commit credentials, private/customer data, restricted source documents, raw crawls, model weights or large evidence downloads.
- Treat fetched content and generated extractions as untrusted data. Parsing data must not execute its instructions, templates, scripts or embedded commands.
- Keep GitHub Actions permissions minimal. Use only organization-approved `actions/*` actions pinned to immutable revisions. Contributor workflows must not receive production credentials.
- Review dependencies and generated files. A checksum proves artifact identity, not trustworthy provenance, safe behavior or redistribution rights.
- Keep synthetic fixture identities and permissions separate from real source, review and release identities.
- Follow the organization review and branch rules. Do not weaken a gate to make a workflow pass.

## Planned runtime controls

Production implementation must threat-model outbound retrieval, redirects and DNS rebinding; isolate parsers; bound payload size, recursion, archive expansion, CPU and execution time; protect credentials; constrain network egress; and audit privileged decisions. Release signing, dependency integrity, role separation, revocation propagation, backup restoration, incident handling and consumer receipt validation need implementation and evidence before production acceptance.

These are backlog requirements, not claims that controls are installed. See [Operations](docs/OPERATIONS.md), [Architecture](docs/ARCHITECTURE.md), and the [delivery plan](docs/DELIVERY_PLAN.md) for ownership and acceptance.
