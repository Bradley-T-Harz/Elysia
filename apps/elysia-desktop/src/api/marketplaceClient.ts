import {
  fetchMarketplaceLinkStatus,
  linkMarketplaceAccount,
  unlinkMarketplaceAccount,
  type EnvelopeResult,
  type MarketplaceLinkEnvelope,
  type MarketplaceLinkStatus
} from "./bridgeClient";
import { governedExternalFetch } from "./internetMaster";

const MARKETPLACE_SESSION_KEY = "elysia_marketplace_session_v0";
export const LOCAL_PROFILE_SESSION_OWNER_KEY = "elysia.local.profile.session-owner.v1";
export const MARKETPLACE_AUTH_CHANGED_EVENT = "elysia-marketplace-auth-changed";

const marketplaceUrl = import.meta.env.VITE_ELYSIA_MARKETPLACE_URL as string | undefined;
const supabaseUrl = import.meta.env.VITE_MARKETPLACE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_MARKETPLACE_SUPABASE_ANON_KEY as string | undefined;

export type MarketplaceConfigStatus = {
  configured: boolean;
  marketplaceUrl?: string;
  missing: string[];
};

export type MarketplaceSession = {
  access_token: string;
  refresh_token?: string;
  expires_at?: number;
  user: {
    id: string;
    email?: string | null;
  };
};

export type MarketplacePublicProfile = {
  id?: string;
  username?: string | null;
  display_name?: string | null;
  bio?: string | null;
  interests?: string | null;
  avatar_url?: string | null;
  is_developer?: boolean | null;
  is_admin?: boolean | null;
};

export type MarketplacePublicSyncField = "username" | "display_name" | "bio" | "interests";

export type MarketplaceSignInResult = {
  ok: boolean;
  session?: MarketplaceSession | null;
  profile?: MarketplacePublicProfile | null;
  message: string;
};

export function getMarketplaceConfigStatus(): MarketplaceConfigStatus {
  const missing: string[] = [];
  if (!supabaseUrl) missing.push("VITE_MARKETPLACE_SUPABASE_URL");
  if (!supabaseAnonKey) missing.push("VITE_MARKETPLACE_SUPABASE_ANON_KEY");
  if (!marketplaceUrl) missing.push("VITE_ELYSIA_MARKETPLACE_URL");
  return {
    configured: missing.length === 0,
    marketplaceUrl,
    missing
  };
}

function isMarketplaceSession(value: unknown): value is MarketplaceSession {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<MarketplaceSession>;
  return Boolean(candidate.access_token && candidate.user?.id);
}

function parseStoredSession(): MarketplaceSession | null {
  try {
    const activeLocalUserId = sessionStorage.getItem(LOCAL_PROFILE_SESSION_OWNER_KEY);
    const raw = sessionStorage.getItem(MARKETPLACE_SESSION_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      sessionStorage.removeItem(MARKETPLACE_SESSION_KEY);
      return null;
    }
    const stored = parsed as { local_user_id?: string; session?: unknown };
    const session = isMarketplaceSession(stored.session) ? stored.session : null;
    const owner = typeof stored.local_user_id === "string" ? stored.local_user_id : null;
    if (!activeLocalUserId || owner !== activeLocalUserId || !session) {
      sessionStorage.removeItem(MARKETPLACE_SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

function storeSession(session: MarketplaceSession | null) {
  if (!session) {
    sessionStorage.removeItem(MARKETPLACE_SESSION_KEY);
    return;
  }
  const localUserId = sessionStorage.getItem(LOCAL_PROFILE_SESSION_OWNER_KEY);
  if (!localUserId) {
    throw new Error("A local Elysia profile must be active before Marketplace credentials can be isolated.");
  }
  sessionStorage.setItem(MARKETPLACE_SESSION_KEY, JSON.stringify({ local_user_id: localUserId, session }));
}

export function clearMarketplaceSessionForLocalProfile(): void {
  storeSession(null);
  notifyMarketplaceAuthChanged("local_profile_changed");
}

function notifyMarketplaceAuthChanged(reason: string) {
  window.dispatchEvent(
    new CustomEvent(MARKETPLACE_AUTH_CHANGED_EVENT, {
      detail: { reason }
    })
  );
}

export function getMarketplaceSession(): MarketplaceSession | null {
  return parseStoredSession();
}

function buildSupabaseUrl(path: string): string {
  if (!supabaseUrl) {
    throw new Error("Marketplace Supabase URL is not configured.");
  }
  return `${supabaseUrl.replace(/\/$/, "")}${path}`;
}

function getSupabaseHeaders(session?: MarketplaceSession | null): HeadersInit {
  if (!supabaseAnonKey) {
    throw new Error("Marketplace Supabase anon key is not configured.");
  }
  return {
    apikey: supabaseAnonKey,
    Authorization: `Bearer ${session?.access_token ?? supabaseAnonKey}`,
    "Content-Type": "application/json"
  };
}

export async function signInToMarketplace(
  email: string,
  password: string
): Promise<MarketplaceSignInResult> {
  const config = getMarketplaceConfigStatus();
  if (!config.configured) {
    return {
      ok: false,
      message: `Marketplace sign-in is not configured. Missing: ${config.missing.join(", ")}.`
    };
  }

  try {
    const response = await governedExternalFetch(buildSupabaseUrl("/auth/v1/token?grant_type=password"), {
      method: "POST",
      headers: getSupabaseHeaders(),
      body: JSON.stringify({ email, password })
    });
    const payload = await response.json();
    if (!response.ok) {
      return {
        ok: false,
        message: String(payload?.error_description || payload?.msg || payload?.message || "Marketplace sign-in failed.")
      };
    }

    const expiresIn = Number(payload.expires_in ?? 0);
    const session: MarketplaceSession = {
      access_token: String(payload.access_token),
      refresh_token: payload.refresh_token ? String(payload.refresh_token) : undefined,
      expires_at: expiresIn ? Math.floor(Date.now() / 1000) + expiresIn : undefined,
      user: {
        id: String(payload.user?.id ?? ""),
        email: payload.user?.email ?? email
      }
    };
    storeSession(session);
    const profile = await fetchMarketplacePublicProfile(session);
    notifyMarketplaceAuthChanged("signed_in");
    return {
      ok: true,
      session,
      profile,
      message: `Signed in to Marketplace as ${session.user.email ?? email}.`
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Marketplace sign-in failed before a response was received."
    };
  }
}

export function signOutOfMarketplace(): MarketplaceSignInResult {
  storeSession(null);
  notifyMarketplaceAuthChanged("signed_out");
  return {
    ok: true,
    session: null,
    message: "Signed out of Marketplace session in this desktop chamber."
  };
}

export async function fetchMarketplacePublicProfile(
  session: MarketplaceSession = getMarketplaceSession() as MarketplaceSession
): Promise<MarketplacePublicProfile | null> {
  if (!session?.user.id) return null;
  const basePath = `/rest/v1/profiles?id=eq.${encodeURIComponent(session.user.id)}`;
  const response = await governedExternalFetch(buildSupabaseUrl(`${basePath}&select=id,username,display_name,bio,interests,avatar_url,is_developer,is_admin`), {
    headers: getSupabaseHeaders(session)
  });
  if (!response.ok) {
    const fallbackResponse = await governedExternalFetch(buildSupabaseUrl(`${basePath}&select=id,username,display_name,bio,avatar_url,is_developer,is_admin`), {
      headers: getSupabaseHeaders(session)
    });
    if (!fallbackResponse.ok) return null;
    const fallbackRows = (await fallbackResponse.json()) as MarketplacePublicProfile[];
    return fallbackRows[0] ?? null;
  }
  const rows = (await response.json()) as MarketplacePublicProfile[];
  return rows[0] ?? null;
}

export async function syncMarketplacePublicProfileFields(
  _fields: Partial<Record<MarketplacePublicSyncField, string>>,
  _selectedFields: MarketplacePublicSyncField[]
): Promise<EnvelopeResult<MarketplaceLinkEnvelope>> {
  return {
    ok: false,
    payload: {
      status: "blocked",
      errors: [
        "Marketplace profile sync is retired. Commons Profile is edited online; Personal Identity, Story, local photos, memory, files, vaults, logs, and chats stay local."
      ],
      data: {
        marketplace_link: {
          linked: false
        } satisfies MarketplaceLinkStatus
      }
    }
  };
}

export async function fetchLocalMarketplaceLink(): Promise<
  EnvelopeResult<MarketplaceLinkEnvelope>
> {
  return fetchMarketplaceLinkStatus();
}

export async function linkCurrentMarketplaceSession(
  profile?: MarketplacePublicProfile | null
): Promise<EnvelopeResult<MarketplaceLinkEnvelope>> {
  const session = getMarketplaceSession();
  if (!session?.user.id) {
    return {
      ok: false,
      payload: {
        status: "blocked",
        errors: ["Sign in to Marketplace before linking."],
        data: {
          marketplace_link: {
            linked: false
          } satisfies MarketplaceLinkStatus
        }
      }
    };
  }

  const result = await linkMarketplaceAccount({
    marketplace_user_id: session.user.id,
    marketplace_email: session.user.email ?? null,
    marketplace_username: profile?.username ?? profile?.display_name ?? session.user.email ?? null,
    sync_enabled_fields: []
  });
  if (result.ok && result.payload.status === "ok") {
    notifyMarketplaceAuthChanged("linked");
  }
  return result;
}

export async function unlinkLocalMarketplaceAccount(): Promise<
  EnvelopeResult<MarketplaceLinkEnvelope>
> {
  const result = await unlinkMarketplaceAccount();
  if (result.ok && result.payload.status === "ok") {
    notifyMarketplaceAuthChanged("unlinked");
  }
  return result;
}

export function getMarketplaceUrl(): string | undefined {
  return marketplaceUrl;
}
