#!/usr/bin/env python3
"""Fail-closed verification of one signed immutable Elysia candidate family."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.install.release_trust import ReleaseTrustError, verify_release_artifact


def verify_family(
    *,
    artifacts_dir: Path,
    manifest_path: Path,
    signature_path: Path,
    trust_policy_path: Path,
) -> dict[str, object]:
    root = artifacts_dir.resolve(strict=True)
    if root.is_symlink() or not root.is_dir():
        raise ReleaseTrustError("The candidate artifact root is unsafe.")

    try:
        manifest_name = json.loads(manifest_path.read_text(encoding="utf-8"))[
            "artifact_filename"
        ]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ReleaseTrustError("The candidate family manifest is unreadable.") from exc
    manifest = verify_release_artifact(
        artifact_path=root / manifest_name,
        manifest_path=manifest_path,
        signature_path=signature_path,
        trust_policy_path=trust_policy_path,
    )
    if not manifest.file_inventory:
        raise ReleaseTrustError("The signed candidate family inventory is empty.")

    actual_files = {
        path.name: path
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if set(actual_files) != set(manifest.file_inventory):
        raise ReleaseTrustError("The candidate artifact directory differs from the signed family inventory.")

    for filename, expected_sha256 in sorted(manifest.file_inventory.items()):
        if sha256(actual_files[filename].read_bytes()).hexdigest() != expected_sha256:
            raise ReleaseTrustError("A candidate artifact differs from its signed family digest.")

    return {
        "status": "passed",
        "release_id": manifest.release_id,
        "version": manifest.version,
        "channel": manifest.channel,
        "signing_key_id": manifest.signing_key_id,
        "artifact_count": len(actual_files),
        "exact_directory_match": True,
        "all_hashes_match": True,
        "private_material_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--trust-policy", type=Path, required=True)
    args = parser.parse_args()
    result = verify_family(
        artifacts_dir=args.artifacts_dir,
        manifest_path=args.manifest,
        signature_path=args.signature,
        trust_policy_path=args.trust_policy,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
