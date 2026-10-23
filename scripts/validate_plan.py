#!/usr/bin/env python3
"""Validate local planning contracts and cross-file relationships."""
from __future__ import annotations

import argparse
from pathlib import Path

from planlib import iter_records, load_bundle, validate_repository


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="repository root")
    args = parser.parse_args(argv)
    errors = validate_repository(args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Plan validation failed: {len(errors)} error(s).")
        return 1
    bundle = load_bundle(args.root)
    records = list(iter_records(bundle["backlog"]))
    print(f"Plan valid: {len(records)} stable records, {len(bundle['coverage']['domains'])} ecosystem domains, "
          f"{len(bundle['decisions']['decisions'])} decisions, {len(bundle['releases']['phases'])} release phases.")
    print("Offline structure and consistency only; no source rights, remote review, GitHub setup or deployment is certified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
