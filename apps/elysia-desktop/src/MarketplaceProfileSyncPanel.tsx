import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  fetchLocalMarketplaceLink,
  getMarketplaceSession,
  MARKETPLACE_AUTH_CHANGED_EVENT
} from "./api/marketplaceClient";
import type { MarketplaceLinkStatus } from "./api/bridgeClient";
import type { AccountProfilePrivate } from "./api/bridgeClient";
import { accountPalette } from "./accountPresentation";

type MarketplaceProfileSyncPanelProps = {
  profile: AccountProfilePrivate;
};

export default function MarketplaceProfileSyncPanel({ profile }: MarketplaceProfileSyncPanelProps) {
  const [linkStatus, setLinkStatus] = useState<MarketplaceLinkStatus | null>(null);

  async function refresh() {
    const linkResult = await fetchLocalMarketplaceLink();
    const nextLink = linkResult.ok && linkResult.payload.status === "ok"
      ? linkResult.payload.data?.marketplace_link ?? null
      : null;
    setLinkStatus(nextLink);
  }

  useEffect(() => {
    void refresh();
    function handleMarketplaceAuthChanged() {
      void refresh();
    }
    window.addEventListener(MARKETPLACE_AUTH_CHANGED_EVENT, handleMarketplaceAuthChanged);
    window.addEventListener("focus", handleMarketplaceAuthChanged);
    return () => {
      window.removeEventListener(MARKETPLACE_AUTH_CHANGED_EVENT, handleMarketplaceAuthChanged);
      window.removeEventListener("focus", handleMarketplaceAuthChanged);
    };
  }, []);

  const session = getMarketplaceSession();
  const accountMatch = Boolean(
    session?.user.id &&
    linkStatus?.linked &&
    linkStatus.marketplace_user_id === session.user.id
  );

  return (
    <section style={panelStyle}>
      <div style={eyebrowStyle}>Marketplace Link Boundary</div>
      <h3 style={{ margin: "0.16rem 0 0.35rem" }}>Add-ons account access only</h3>
      <p style={bodyStyle}>
        Marketplace Link is for add-ons and online account functions only. It does not sync Personal Identity,
        Story, local photos, memory, files, vaults, logs, chats, or request traces.
      </p>

      <div style={factsStyle}>
        <Fact label="Local identity" value={profile.username || "Authenticated"} />
        <Fact label="Marketplace session" value={session?.user.email ? `Signed in as ${session.user.email}` : "Not signed in"} />
        <Fact label="Linked account" value={linkStatus?.linked ? linkStatus.marketplace_email ?? linkStatus.marketplace_username ?? "Linked" : "Not linked"} />
        <Fact label="Account match" value={accountMatch ? "Matched" : "Not ready"} />
        <Fact label="Backend stores tokens" value="No" />
        <Fact label="Private identity shared" value="No" />
      </div>

      <div style={splitGridStyle}>
        <section style={miniPanelStyle}>
          <div style={eyebrowStyle}>Allowed capabilities</div>
          <ul style={listStyle}>
            <li>Marketplace add-ons</li>
            <li>Install intents</li>
            <li>Compatibility checks</li>
            <li>Account-gated Marketplace functions</li>
          </ul>
        </section>
        <section style={miniPanelStyle}>
          <div style={eyebrowStyle}>Never synced</div>
          <ul style={listStyle}>
            <li>Personal Identity or Story</li>
            <li>Interests, local photos, or private contact details</li>
            <li>Memory, files, vaults, logs, chats, or request traces</li>
            <li>Passwords, tokens, credentials, or machine data</li>
          </ul>
        </section>
      </div>

      <div style={plannedStyle}>
        Public profile sync has been retired. Commons Profile is edited online; Personal Identity stays sealed and local-first.
        Future linking should prefer browser/device-code or PKCE-style pairing over password entry inside the desktop UI.
      </div>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div style={factStyle}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
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

const bodyStyle: CSSProperties = {
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

const splitGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "0.75rem"
};

const miniPanelStyle: CSSProperties = {
  padding: "0.8rem",
  borderRadius: "13px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.28)"
};

const listStyle: CSSProperties = {
  margin: "0.5rem 0 0",
  paddingLeft: "1.1rem",
  color: accountPalette.silverMuted,
  lineHeight: 1.55
};

const plannedStyle: CSSProperties = {
  border: "1px dashed rgba(184, 162, 123, 0.34)",
  borderRadius: "13px",
  padding: "0.75rem",
  color: accountPalette.silverMuted,
  background: "rgba(11, 14, 18, 0.32)",
  lineHeight: 1.5
};
