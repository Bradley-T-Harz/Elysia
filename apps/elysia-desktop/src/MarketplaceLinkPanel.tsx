import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import {
  fetchLocalMarketplaceLink,
  fetchMarketplacePublicProfile,
  getMarketplaceConfigStatus,
  getMarketplaceSession,
  getMarketplaceUrl,
  linkCurrentMarketplaceSession,
  MARKETPLACE_AUTH_CHANGED_EVENT,
  signInToMarketplace,
  signOutOfMarketplace,
  unlinkLocalMarketplaceAccount,
  type MarketplacePublicProfile,
  type MarketplaceSession
} from "./api/marketplaceClient";
import type { MarketplaceLinkStatus } from "./api/bridgeClient";
import { accountPalette, readEnvelopeError } from "./accountPresentation";

export default function MarketplaceLinkPanel() {
  const config = useMemo(() => getMarketplaceConfigStatus(), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [session, setSession] = useState<MarketplaceSession | null>(() => getMarketplaceSession());
  const [profile, setProfile] = useState<MarketplacePublicProfile | null>(null);
  const [linkStatus, setLinkStatus] = useState<MarketplaceLinkStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function loadLinkStatus() {
    const result = await fetchLocalMarketplaceLink();
    if (result.ok && result.payload.status === "ok") {
      setLinkStatus(result.payload.data?.marketplace_link ?? null);
      return;
    }
    setMessage(readEnvelopeError(result.payload));
  }

  async function refreshMarketplaceState() {
    const existing = getMarketplaceSession();
    setSession(existing);
    if (existing) {
      setProfile(await fetchMarketplacePublicProfile(existing));
    } else {
      setProfile(null);
    }
    await loadLinkStatus();
  }

  useEffect(() => {
    void refreshMarketplaceState();
    function handleMarketplaceAuthChanged() {
      void refreshMarketplaceState();
    }
    window.addEventListener(MARKETPLACE_AUTH_CHANGED_EVENT, handleMarketplaceAuthChanged);
    return () => {
      window.removeEventListener(MARKETPLACE_AUTH_CHANGED_EVENT, handleMarketplaceAuthChanged);
    };
  }, []);

  async function handleSignIn() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await signInToMarketplace(email, password);
      setMessage(result.message);
      setSession(result.session ?? null);
      setProfile(result.profile ?? null);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  function handleSignOut() {
    const result = signOutOfMarketplace();
    setSession(null);
    setProfile(null);
    setMessage(result.message);
  }

  async function handleLink() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await linkCurrentMarketplaceSession(profile);
      if (!result.ok || result.payload.status !== "ok") {
        setMessage(readEnvelopeError(result.payload));
        return;
      }
      setLinkStatus(result.payload.data?.marketplace_link ?? null);
      const nextStatus = result.payload.data?.marketplace_link ?? null;
      setMessage(
        `Linked to Marketplace account ${nextStatus?.marketplace_email ?? nextStatus?.marketplace_username ?? session?.user.email ?? "linked account"}.`
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleUnlink() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await unlinkLocalMarketplaceAccount();
      if (!result.ok || result.payload.status !== "ok") {
        setMessage(readEnvelopeError(result.payload));
        return;
      }
      setLinkStatus(result.payload.data?.marketplace_link ?? null);
      setMessage("Marketplace account unlinked.");
    } finally {
      setBusy(false);
    }
  }

  const signedInLabel = session?.user.email ? `Signed in as ${session.user.email}` : "Not signed in to Marketplace";
  const linkedLabel = linkStatus?.linked
    ? `Linked to ${linkStatus.marketplace_email ?? linkStatus.marketplace_username ?? "Marketplace profile"}`
    : "Not linked";
  const signedInButNotLinked = Boolean(session && !linkStatus?.linked);
  const marketplaceUrl = getMarketplaceUrl();

  return (
    <section style={panelStyle}>
      <div style={eyebrowStyle}>Marketplace Link</div>
      <h3 style={{ margin: "0.18rem 0 0.35rem" }}>Marketplace account link</h3>
      <p style={bodyTextStyle}>
        This links the local chamber to Elysia Ecobotics Online for Marketplace add-ons and account-gated Marketplace functions only. It does not sync Personal Identity, Story, local photos, memory, files, vaults, logs, or chats.
      </p>

      {!config.configured && (
        <div style={warningStyle}>
          Marketplace linking is not configured. Missing: {config.missing.join(", ")}.
        </div>
      )}

      <dl style={factsStyle}>
        <div style={factStyle}><dt>Marketplace session</dt><dd>{signedInLabel}</dd></div>
        <div style={factStyle}><dt>Local link</dt><dd>{linkedLabel}</dd></div>
        <div style={factStyle}><dt>Backend stores tokens</dt><dd>No</dd></div>
        <div style={factStyle}><dt>Personal Identity shared</dt><dd>No</dd></div>
        <div style={factStyle}><dt>Allowed capabilities</dt><dd>Marketplace add-ons, install intents, compatibility checks</dd></div>
      </dl>

      {signedInButNotLinked && (
        <div style={linkPromptStyle}>
          Marketplace is signed in. Use <strong>Link Marketplace Account</strong> to unlock Add-ons for this local Elysia chamber.
        </div>
      )}

      <div style={formGridStyle}>
        <label style={labelStyle}>
          <span>Marketplace email</span>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            type="email"
            placeholder="marketplace@example.com"
            autoComplete="email"
            style={inputStyle}
          />
        </label>
        <label style={labelStyle}>
          <span>Marketplace password</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            placeholder="Supabase Marketplace password"
            autoComplete="current-password"
            style={inputStyle}
          />
        </label>
      </div>

      <div style={actionRowStyle}>
        <button type="button" onClick={handleSignIn} disabled={!config.configured || busy} style={primaryButtonStyle}>
          {busy ? "Working..." : "Sign in to Marketplace"}
        </button>
        <button type="button" onClick={handleLink} disabled={!session || busy} style={signedInButNotLinked ? primaryButtonStyle : secondaryButtonStyle}>
          Link Marketplace Account
        </button>
        <button type="button" onClick={handleSignOut} disabled={!session || busy} style={secondaryButtonStyle}>
          Sign out Marketplace
        </button>
        <button type="button" onClick={handleUnlink} disabled={busy || !linkStatus?.linked} style={secondaryButtonStyle}>
          Unlink Marketplace
        </button>
        {marketplaceUrl && (
          <a href={marketplaceUrl} target="_blank" rel="noreferrer" style={linkStyle}>
            Open Marketplace
          </a>
        )}
      </div>

      {message && <div style={statusStyle}>{message}</div>}

      <div style={privacyNoteStyle}>
        Runtime/chat do not receive Marketplace sessions, Supabase tokens, Personal Identity fields, Story, local photos, memory, files, vaults, logs, chats, request traces, dependency inventory, or local paths. Long-term account linking should move toward browser/device-code or PKCE-style pairing rather than password entry in this desktop surface.
      </div>
    </section>
  );
}

const panelStyle: CSSProperties = {
  padding: "1rem",
  borderRadius: "16px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.36)",
  display: "grid",
  gap: "0.8rem",
  minWidth: 0
};

const eyebrowStyle: CSSProperties = {
  fontSize: "0.7rem",
  letterSpacing: "0.11em",
  textTransform: "uppercase",
  color: accountPalette.sandstone
};

const bodyTextStyle: CSSProperties = {
  margin: 0,
  color: accountPalette.silverMuted,
  lineHeight: 1.55
};

const factsStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "0.65rem",
  margin: 0
};

const factStyle: CSSProperties = {
  padding: "0.75rem",
  borderRadius: "13px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.34)",
  overflowWrap: "anywhere"
};

const formGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "0.75rem"
};

const labelStyle: CSSProperties = {
  display: "grid",
  gap: "0.36rem",
  fontWeight: 700
};

const inputStyle: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "12px",
  background: "rgba(11, 14, 18, 0.48)",
  color: accountPalette.silver,
  padding: "0.72rem 0.78rem",
  font: "inherit"
};

const actionRowStyle: CSSProperties = {
  display: "flex",
  gap: "0.65rem",
  flexWrap: "wrap",
  alignItems: "center"
};

const primaryButtonStyle: CSSProperties = {
  border: "1px solid rgba(126, 215, 209, 0.34)",
  borderRadius: "12px",
  padding: "0.72rem 0.9rem",
  background: "linear-gradient(180deg, rgba(16, 71, 75, 0.74) 0%, rgba(18, 25, 37, 0.88) 100%)",
  color: accountPalette.silver,
  cursor: "pointer",
  fontWeight: 800
};

const secondaryButtonStyle: CSSProperties = {
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "12px",
  padding: "0.72rem 0.9rem",
  background: accountPalette.panelSoft,
  color: accountPalette.silver,
  cursor: "pointer"
};

const linkStyle: CSSProperties = {
  ...secondaryButtonStyle,
  textDecoration: "none",
  display: "inline-flex",
  alignItems: "center"
};

const statusStyle: CSSProperties = {
  padding: "0.78rem",
  borderRadius: "13px",
  border: "1px solid rgba(126, 215, 209, 0.28)",
  background: "rgba(126, 215, 209, 0.08)",
  color: accountPalette.silver,
  overflowWrap: "anywhere"
};

const warningStyle: CSSProperties = {
  padding: "0.78rem",
  borderRadius: "13px",
  border: "1px solid rgba(184, 162, 123, 0.34)",
  background: "rgba(184, 162, 123, 0.08)",
  color: accountPalette.sandstone,
  overflowWrap: "anywhere"
};

const linkPromptStyle: CSSProperties = {
  padding: "0.78rem",
  borderRadius: "13px",
  border: "1px solid rgba(126, 215, 209, 0.3)",
  background: "rgba(126, 215, 209, 0.08)",
  color: accountPalette.silver,
  lineHeight: 1.5,
  overflowWrap: "anywhere"
};

const privacyNoteStyle: CSSProperties = {
  padding: "0.85rem",
  borderRadius: "13px",
  border: "1px dashed rgba(184, 162, 123, 0.34)",
  color: accountPalette.silverMuted,
  lineHeight: 1.55,
  background: "rgba(11, 14, 18, 0.32)"
};
