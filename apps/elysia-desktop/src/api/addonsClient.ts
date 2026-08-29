import {
  fetchLocalMarketplaceLink,
  getMarketplaceConfigStatus,
  getMarketplaceSession,
  getMarketplaceUrl,
  MARKETPLACE_AUTH_CHANGED_EVENT,
  type MarketplaceSession
} from "./marketplaceClient";
import type { MarketplaceLinkStatus } from "./bridgeClient";
import { governedExternalFetch } from "./internetMaster";
import {
  applyAddonTransition,
  approveAddonTransition,
  createAddonTransitionPlan,
  fetchAddonAudit,
  fetchAddonInstallerStatus,
  fetchInstalledAddons,
  inspectAddonPackage,
  planAddonAction,
  testAddonSandbox,
  type AddonActionPlan,
  type AddonTransitionAction
} from "./bridgeClient";

export { MARKETPLACE_AUTH_CHANGED_EVENT };

const supabaseUrl = import.meta.env.VITE_MARKETPLACE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_MARKETPLACE_SUPABASE_ANON_KEY as string | undefined;

export type AddonDependency = {
  ecosystem: string;
  package_name: string;
  source?: string;
  version_constraint?: string;
  required: boolean;
};

export type AddonAction = {
  action_key: string;
  action_label: string;
  action_kind: string;
  allowed: boolean;
  risk_level: string;
  requires_local_operator_password: boolean;
  network_access?: boolean;
  notes: string[];
};

export type AddonManifest = {
  schema_version: string;
  id: string;
  name: string;
  publisher: string;
  version: string;
  category: string;
  summary: string;
  description: string;
  trust_tier: string;
  local_only: boolean;
  network_access: boolean;
  dependencies: AddonDependency[];
  actions: AddonAction[];
  security: {
    operator_only: boolean;
    model_accessible: boolean;
    chat_accessible: boolean;
    memory_promotion_allowed: boolean;
    outward_sharing_allowed: boolean;
    local_file_access: string;
    outward_sharing_risk?: string;
  };
  tags: string[];
  homepage_url?: string;
  source_url?: string;
  license?: string;
  status?: string;
};

export type AddonsGateState = {
  unlocked: boolean;
  reason: string;
  session: MarketplaceSession | null;
  link: MarketplaceLinkStatus | null;
  marketplaceUrl?: string;
};

export type AddonActionPlanResult = AddonActionPlan;
export type LocalAddonInstallerData = Record<string, unknown>;
export type LocalAddonTransitionPlan = Record<string, unknown>;

type AddonRow = {
  slug: string;
  name: string;
  summary: string;
  description: string;
  category: string;
  trust_tier: string;
  latest_version?: string | null;
  homepage_url?: string | null;
  source_url?: string | null;
  license?: string | null;
  local_only?: boolean | null;
  network_access?: boolean | null;
  addon_versions?: { manifest?: AddonManifest; review_status?: string }[] | null;
};

function buildSupabaseUrl(path: string): string {
  if (!supabaseUrl) {
    throw new Error("Marketplace Supabase URL is not configured.");
  }
  return `${supabaseUrl.replace(/\/$/, "")}${path}`;
}

function getSupabaseHeaders(session: MarketplaceSession): HeadersInit {
  if (!supabaseAnonKey) {
    throw new Error("Marketplace Supabase anon key is not configured.");
  }
  return {
    apikey: supabaseAnonKey,
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json"
  };
}

function safeProfileNameFromSession(session: MarketplaceSession): { username: string; displayName: string } {
  const emailPrefix = (session.user.email ?? "")
    .split("@")[0]
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32);
  const shortId = session.user.id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 10) || "user";
  const usernameBase = emailPrefix || "marketplace_user";
  return {
    username: `${usernameBase}_${shortId}`.slice(0, 63),
    displayName: emailPrefix || `user_${shortId}`
  };
}

export async function ensureMarketplaceProfile(session: MarketplaceSession): Promise<void> {
  if (!session?.user.id) {
    throw new Error("Marketplace session is missing; sign in before saving add-ons.");
  }
  const profileParams = new URLSearchParams({
    select: "id",
    id: `eq.${session.user.id}`,
    limit: "1"
  });
  const existing = await governedExternalFetch(buildSupabaseUrl(`/rest/v1/profiles?${profileParams.toString()}`), {
    headers: getSupabaseHeaders(session)
  });
  if (existing.ok) {
    const rows = (await existing.json()) as { id?: string }[];
    if (rows.length > 0) return;
  }

  const fallback = safeProfileNameFromSession(session);
  const created = await governedExternalFetch(buildSupabaseUrl("/rest/v1/profiles"), {
    method: "POST",
    headers: {
      ...getSupabaseHeaders(session),
      Prefer: "resolution=ignore-duplicates"
    },
    body: JSON.stringify({
      id: session.user.id,
      username: fallback.username,
      display_name: fallback.displayName
    })
  });
  if (!created.ok) {
    const text = await created.text();
    throw new Error(`Marketplace profile row is missing. Create or refresh Marketplace profile, then try again. ${text || created.statusText}`);
  }
}

function rowToManifest(row: AddonRow): AddonManifest {
  const approvedManifest = row.addon_versions?.find(
    (version) => version.review_status === "approved" && version.manifest
  )?.manifest;
  if (approvedManifest) return approvedManifest;

  const networkAccess = Boolean(row.network_access);
  return {
    schema_version: "1.0",
    id: row.slug,
    name: row.name,
    publisher: "Marketplace",
    version: row.latest_version ?? "1.0.0",
    category: row.category,
    summary: row.summary,
    description: row.description,
    trust_tier: row.trust_tier,
    local_only: row.local_only ?? !networkAccess,
    network_access: networkAccess,
    dependencies: [],
    actions: [
      {
        action_key: "review_manifest",
        action_label: "Review manifest",
        action_kind: "manual_instruction",
        allowed: true,
        risk_level: networkAccess ? "moderate" : "low",
        requires_local_operator_password: true,
        network_access: networkAccess,
        notes: [
          "Remote listing did not include a rich manifest version.",
          "Local Elysia execution is not implemented in this Sprint 2 room."
        ]
      }
    ],
    security: {
      operator_only: true,
      model_accessible: false,
      chat_accessible: false,
      memory_promotion_allowed: false,
      outward_sharing_allowed: networkAccess,
      local_file_access: "none"
    },
    tags: [row.category, row.trust_tier],
    homepage_url: row.homepage_url ?? undefined,
    source_url: row.source_url ?? undefined,
    license: row.license ?? undefined,
    status: "approved"
  };
}

export async function getAddonsGateState(): Promise<AddonsGateState> {
  const config = getMarketplaceConfigStatus();
  const session = getMarketplaceSession();
  const marketplaceUrl = getMarketplaceUrl();
  if (!config.configured) {
    return {
      unlocked: false,
      reason: `Marketplace is not configured. Missing: ${config.missing.join(", ")}.`,
      session: null,
      link: null,
      marketplaceUrl
    };
  }
  if (!session?.user.id) {
    return {
      unlocked: false,
      reason: "Sign in to Marketplace in Personal Identity to use Add-ons.",
      session: null,
      link: null,
      marketplaceUrl
    };
  }

  const linkResult = await fetchLocalMarketplaceLink();
  const link = linkResult.ok && linkResult.payload.status === "ok"
    ? linkResult.payload.data?.marketplace_link ?? null
    : null;

  if (!link?.linked) {
    return {
      unlocked: false,
      reason: "Marketplace is signed in, but this local Elysia profile is not linked yet.",
      session,
      link,
      marketplaceUrl
    };
  }

  if (link.marketplace_user_id !== session.user.id) {
    return {
      unlocked: false,
      reason: "You are signed into a different Marketplace account than the one linked to this local Elysia profile.",
      session,
      link,
      marketplaceUrl
    };
  }

  return {
    unlocked: true,
    reason: `Marketplace gate unlocked for ${session.user.email ?? link.marketplace_email ?? "linked account"}.`,
    session,
    link,
    marketplaceUrl
  };
}

export async function fetchApprovedMarketplaceAddons(
  session: MarketplaceSession
): Promise<AddonManifest[]> {
  const params = new URLSearchParams({
    select: "*,addon_versions(manifest,review_status,published_at)",
    status: "eq.approved",
    order: "name.asc"
  });
  const response = await governedExternalFetch(buildSupabaseUrl(`/rest/v1/addons?${params.toString()}`), {
    headers: getSupabaseHeaders(session)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Marketplace catalog query failed: ${text || response.statusText}`);
  }
  const rows = (await response.json()) as AddonRow[];
  return rows.map(rowToManifest);
}

export async function fetchSavedAddonSlugs(session: MarketplaceSession): Promise<string[]> {
  const params = new URLSearchParams({
    select: "addon_slug",
    user_id: `eq.${session.user.id}`
  });
  const response = await governedExternalFetch(buildSupabaseUrl(`/rest/v1/user_saved_addons?${params.toString()}`), {
    headers: getSupabaseHeaders(session)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Saved add-ons query failed: ${text || response.statusText}`);
  }
  const rows = (await response.json()) as { addon_slug?: string }[];
  return rows.map((row) => row.addon_slug).filter(Boolean) as string[];
}

export async function saveAddonSlug(session: MarketplaceSession, addonSlug: string): Promise<void> {
  await ensureMarketplaceProfile(session);
  const response = await governedExternalFetch(buildSupabaseUrl("/rest/v1/user_saved_addons"), {
    method: "POST",
    headers: {
      ...getSupabaseHeaders(session),
      Prefer: "resolution=ignore-duplicates"
    },
    body: JSON.stringify({
      user_id: session.user.id,
      addon_slug: addonSlug
    })
  });
  if (!response.ok) {
    const text = await response.text();
    if (text.includes("user_saved_addons_user_id_fkey") || text.includes("Key is not present in table \"profiles\"")) {
      throw new Error("Marketplace profile row is missing. Create or refresh Marketplace profile, then try again.");
    }
    throw new Error(`Save add-on failed: ${text || response.statusText}`);
  }
}

export async function removeSavedAddonSlug(session: MarketplaceSession, addonSlug: string): Promise<void> {
  const params = new URLSearchParams({
    user_id: `eq.${session.user.id}`,
    addon_slug: `eq.${addonSlug}`
  });
  const response = await governedExternalFetch(buildSupabaseUrl(`/rest/v1/user_saved_addons?${params.toString()}`), {
    method: "DELETE",
    headers: getSupabaseHeaders(session)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Remove saved add-on failed: ${text || response.statusText}`);
  }
}

export async function planMarketplaceAddonAction(
  addon: AddonManifest,
  action: AddonAction
): Promise<AddonActionPlan | null> {
  const result = await planAddonAction({
    addon_id: addon.id,
    addon_name: addon.name,
    publisher: addon.publisher,
    action,
    dependencies: addon.dependencies,
    trust_tier: addon.trust_tier,
    local_only: addon.local_only,
    network_access: addon.network_access
  });
  if (!result.ok || result.payload.status !== "ok") {
    throw new Error(result.payload.errors?.[0] ?? "Add-on action planning failed.");
  }
  return result.payload.data?.addon_action_plan ?? null;
}

function readInstallerData(result: Awaited<ReturnType<typeof fetchAddonInstallerStatus>>): LocalAddonInstallerData {
  if (!result.ok || result.payload.status === "error" || result.payload.status === "blocked") {
    throw new Error(result.payload.errors?.[0] ?? "Local add-on installer request failed.");
  }
  return result.payload.data ?? {};
}

export async function loadLocalAddonInstallerStatus(): Promise<LocalAddonInstallerData> {
  return readInstallerData(await fetchAddonInstallerStatus());
}

export async function loadLocalInstalledAddons(): Promise<LocalAddonInstallerData> {
  return readInstallerData(await fetchInstalledAddons());
}

export async function loadLocalAddonAudit(): Promise<LocalAddonInstallerData> {
  return readInstallerData(await fetchAddonAudit());
}

export async function inspectLocalAddonPackage(packagePath: string): Promise<LocalAddonInstallerData> {
  return readInstallerData(await inspectAddonPackage({ package_path: packagePath, source: "manual_file" }));
}

export async function planLocalAddonInstall(packagePath: string): Promise<LocalAddonInstallerData> {
  return readInstallerData(await createAddonTransitionPlan({
    action: "install_disabled",
    package_path: packagePath,
    source: "manual_file",
    actor: "local_operator"
  }));
}

export async function runLocalAddonValidationSandbox(packagePath: string): Promise<LocalAddonInstallerData> {
  return readInstallerData(await testAddonSandbox({ package_path: packagePath, source: "manual_file" }));
}

export async function planLocalAddonTransition(input: {
  action: AddonTransitionAction;
  packagePath?: string;
  addonId?: string;
  version?: string;
  expectedState?: string;
  expectedPackageHash?: string;
}): Promise<LocalAddonInstallerData> {
  return readInstallerData(await createAddonTransitionPlan({
    action: input.action,
    package_path: input.packagePath,
    addon_id: input.addonId,
    version: input.version,
    expected_state: input.expectedState,
    expected_package_hash: input.expectedPackageHash,
    approved_permissions: [],
    actor: "local_operator",
    reason: "Explicit local Add-ons Manager transition plan.",
    source: "manual_file"
  }));
}

export async function approveAndApplyLocalAddonTransition(
  plan: LocalAddonTransitionPlan
): Promise<LocalAddonInstallerData> {
  const planId = String(plan.plan_id ?? "");
  const planHash = String(plan.plan_hash ?? "");
  if (!planId || !planHash || plan.plan_state !== "ready_for_exact_approval") {
    throw new Error("The exact add-on transition plan is missing, blocked, or stale.");
  }
  const approved = readInstallerData(await approveAddonTransition({
    plan_id: planId,
    plan_hash: planHash,
    operator_confirmed: true,
    actor: "local_operator",
    confirmation: "APPROVE EXACT ADD-ON CHANGE"
  }));
  const approval = approved.transition_approval as Record<string, unknown> | undefined;
  const approvalId = String(approval?.approval_id ?? "");
  const approvalToken = String(approval?.approval_token ?? "");
  if (!approvalId || !approvalToken || approval?.approved !== true) {
    throw new Error("Exact add-on transition approval was refused.");
  }
  return readInstallerData(await applyAddonTransition({
    plan_id: planId,
    plan_hash: planHash,
    approval_id: approvalId,
    approval_token: approvalToken
  }));
}

export async function planLocalAddonLifecycleAction(
  entry: Record<string, unknown>,
  action: "enable" | "disable" | "revoke" | "remove"
): Promise<LocalAddonInstallerData> {
  const mapped: AddonTransitionAction = action === "enable" ? "enable_limited" : action;
  return planLocalAddonTransition({
    action: mapped,
    addonId: String(entry.addon_id ?? ""),
    version: String(entry.version ?? ""),
    expectedState: String(entry.status ?? ""),
    expectedPackageHash: String(entry.package_hash ?? "")
  });
}
