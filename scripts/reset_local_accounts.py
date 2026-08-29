#!/usr/bin/env python3
"""Governed local-only account reset after a verified private preservation archive.

This operator utility never handles passwords and is intentionally unavailable
through the HTTP API. It refuses to proceed if any account still owns canonical
Memory, Project, Conversation, or shared-space records.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.api.account_service import (
    OPERATOR_RESET_CONFIRMATION,
    AccountStore,
)


def _verify_archive(root: Path) -> int:
    manifest = root / "SHA256SUMS.txt"
    if not root.is_dir() or root.is_symlink() or not manifest.is_file():
        raise SystemExit("Private preservation archive or SHA-256 manifest is unavailable.")
    entries = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            expected, relative = line.split(maxsplit=1)
        except ValueError as exc:
            raise SystemExit("Private preservation manifest format is invalid.") from exc
        relative = relative.lstrip("* ")
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise SystemExit("Private preservation manifest escapes its archive root.") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise SystemExit("A private preservation archive entry is unavailable.")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit("A private preservation archive hash did not verify.")
        entries += 1
    if entries == 0:
        raise SystemExit("Private preservation manifest contains no verified entries.")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.confirmation != OPERATOR_RESET_CONFIRMATION:
        raise SystemExit("Exact governed reset confirmation was not supplied.")
    verified_entries = _verify_archive(args.archive)
    store = AccountStore()
    store.initialize()
    account_count = store.account_count()
    inventories = []
    with store._connect() as conn:  # operator tool, bounded to aggregate counts
        user_ids = [str(row["id"]) for row in conn.execute("SELECT id FROM users")]
    for user_id in user_ids:
        inventories.append(store.deletion_inventory(user_id))
    blocking = sum(item.blocking_owned_records for item in inventories)
    print(f"preservation_entries_verified={verified_entries}")
    print(f"local_accounts_detected={account_count}")
    print(f"blocking_owned_records={blocking}")
    if blocking:
        raise SystemExit("Reset refused because account-owned records remain.")
    if not args.execute:
        print("dry_run=passed")
        return 0
    result = store.reset_all_accounts_after_verified_preservation(
        confirmation=args.confirmation,
        preservation_verified=True,
    )
    print("reset_executed=true")
    for key in sorted(result):
        print(f"{key}={result[key]}")
    state = store.state()
    print(f"final_accounts={state.account_count}")
    print(f"final_active_sessions={1 if state.is_authenticated else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
