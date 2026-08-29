from __future__ import annotations

from pathlib import Path

import pytest


MARKETPLACE_ROOT = Path(__file__).resolve().parents[2] / "elysia-marketplace"
MIGRATION_PATH = MARKETPLACE_ROOT / "supabase/migrations/2026_06_02_saved_addons_permissions.sql"
BOOTSTRAP_MIGRATION_PATH = MARKETPLACE_ROOT / "supabase/migrations/2026_06_02_profile_bootstrap_for_saved_addons.sql"
POLICIES_PATH = MARKETPLACE_ROOT / "supabase/policies.sql"
ADDONS_CLIENT_PATH = Path("apps/elysia-desktop/src/api/addonsClient.ts")


def test_saved_addons_permission_migration_grants_authenticated_with_rls_guard():
    if not MARKETPLACE_ROOT.exists():
        pytest.skip("Sibling elysia-marketplace repo is not present in this checkout.")

    migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()
    policies = POLICIES_PATH.read_text(encoding="utf-8").lower()
    combined = f"{migration}\n{policies}"

    assert "alter table public.user_saved_addons enable row level security" in migration
    assert "user_id = auth.uid()" in combined
    assert "grant select, insert, delete on table public.user_saved_addons to authenticated" in combined
    assert "service_role" not in migration
    assert "grant all" not in migration
    assert "grant update" not in migration


def test_profile_bootstrap_migration_creates_minimal_profiles_without_admin_promotion():
    if not MARKETPLACE_ROOT.exists():
        pytest.skip("Sibling elysia-marketplace repo is not present in this checkout.")

    migration = BOOTSTRAP_MIGRATION_PATH.read_text(encoding="utf-8").lower()

    assert "insert into public.profiles (id, username, display_name)" in migration
    assert "from auth.users" in migration
    assert "bootstrap_marketplace_profile_for_auth_user" in migration
    assert "after insert on auth.users" in migration
    assert "on conflict (id) do nothing" in migration
    assert "is_admin" not in migration
    assert "is_developer" not in migration
    assert "service_role" not in migration


def test_addons_save_path_ensures_marketplace_profile_before_saved_addon_insert():
    source = ADDONS_CLIENT_PATH.read_text(encoding="utf-8")
    save_index = source.index("export async function saveAddonSlug")
    ensure_index = source.index("await ensureMarketplaceProfile(session);", save_index)
    insert_index = source.index('/rest/v1/user_saved_addons', save_index)

    assert ensure_index < insert_index
    helper_source = source[
        source.index("export async function ensureMarketplaceProfile"):
        source.index("function rowToManifest")
    ]
    assert "Marketplace profile row is missing. Create or refresh Marketplace profile, then try again." in source
    assert "local Elysia" not in helper_source
