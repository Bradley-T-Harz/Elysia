import type { CSSProperties } from "react";
import type { BridgeStartupState } from "./api/bridgeClient";
import { useAccountSession } from "./AccountGate";

type HomePageProps = {
  startupTruthState: BridgeStartupState;
  startupTruthMessage: string;
  startupTruthDetail: string;
  startupReady: boolean;
  bridgeApiVersion?: string;
  bridgeContractVersion?: string;
  runtimeContractVersion?: string;
  capabilityContractVersion?: string;
};

type StatusSurfaceState =
  | "live"
  | "partial"
  | "planned"
  | "inactive"
  | "unavailable"
  | "degraded"
  | "blocked";

const palette = {
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  glowTeal: "rgba(126, 215, 209, 0.16)",
  glowBronze: "rgba(138, 106, 60, 0.14)"
} as const;

function mapStartupTruthToSurfaceState(
  startupTruthState: BridgeStartupState
): StatusSurfaceState {
  switch (startupTruthState) {
    case "ok":
      return "live";
    case "degraded":
      return "degraded";
    case "unavailable":
    case "error":
      return "unavailable";
    case "checking":
    default:
      return "partial";
  }
}

function getStartupTruthCardStyle(state: BridgeStartupState): CSSProperties {
  switch (state) {
    case "ok":
      return {
        border: "1px solid rgba(126, 215, 209, 0.24)",
        background:
          "linear-gradient(180deg, rgba(18, 41, 43, 0.42) 0%, rgba(18, 25, 37, 0.76) 100%)",
        boxShadow: `0 0 0 1px rgba(126, 215, 209, 0.05), 0 0 24px ${palette.glowTeal}`
      };
    case "degraded":
      return {
        border: "1px solid rgba(184, 162, 123, 0.24)",
        background:
          "linear-gradient(180deg, rgba(43, 31, 21, 0.42) 0%, rgba(18, 25, 37, 0.76) 100%)",
        boxShadow: `0 0 0 1px rgba(184, 162, 123, 0.04), 0 0 18px ${palette.glowBronze}`
      };
    case "unavailable":
    case "error":
      return {
        border: "1px solid rgba(139, 78, 47, 0.34)",
        background:
          "linear-gradient(180deg, rgba(48, 23, 17, 0.58) 0%, rgba(18, 25, 37, 0.78) 100%)"
      };
    case "checking":
    default:
      return {
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.76) 100%)"
      };
  }
}

function getStateColors(state: StatusSurfaceState) {
  switch (state) {
    case "live":
      return {
        border: "rgba(126, 215, 209, 0.30)",
        text: palette.teal,
        background: "rgba(126, 215, 209, 0.08)"
      };
    case "partial":
      return {
        border: "rgba(184, 162, 123, 0.34)",
        text: palette.sandstone,
        background: "rgba(184, 162, 123, 0.10)"
      };
    case "planned":
      return {
        border: "rgba(199, 210, 218, 0.22)",
        text: palette.silverMuted,
        background: "rgba(199, 210, 218, 0.08)"
      };
    case "inactive":
      return {
        border: "rgba(199, 210, 218, 0.18)",
        text: palette.silverMuted,
        background: "rgba(199, 210, 218, 0.06)"
      };
    case "unavailable":
      return {
        border: "rgba(216, 165, 165, 0.30)",
        text: "#D8A5A5",
        background: "rgba(216, 165, 165, 0.08)"
      };
    case "degraded":
      return {
        border: "rgba(215, 169, 126, 0.30)",
        text: "#D7A97E",
        background: "rgba(215, 169, 126, 0.08)"
      };
    case "blocked":
      return {
        border: "rgba(189, 115, 115, 0.34)",
        text: "#D69494",
        background: "rgba(189, 115, 115, 0.08)"
      };
    default:
      return {
        border: palette.lineSilver,
        text: palette.silverMuted,
        background: "rgba(199, 210, 218, 0.06)"
      };
  }
}

function StatusBadge({ state }: { state: StatusSurfaceState }) {
  const colors = getStateColors(state);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "0.16rem 0.5rem",
        borderRadius: "999px",
        border: `1px solid ${colors.border}`,
        background: colors.background,
        color: colors.text,
        fontSize: "0.68rem",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        whiteSpace: "nowrap"
      }}
    >
      {state}
    </span>
  );
}

export default function HomePage({
  startupTruthState,
  startupTruthMessage,
  startupTruthDetail,
  startupReady,
  bridgeApiVersion,
  bridgeContractVersion,
  runtimeContractVersion,
  capabilityContractVersion
}: HomePageProps) {
  const startupSurfaceState = mapStartupTruthToSurfaceState(startupTruthState);
  const { state, logout } = useAccountSession();

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      data-testid="home-page-scroll"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        minHeight: 0,
        flex: 1
      }}
    >
      <div>
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: palette.sandstone,
            marginBottom: "0.4rem"
          }}
        >
          Chamber
        </div>
        <h1
          style={{
            margin: 0,
            fontSize: "2.15rem",
            lineHeight: 1.1
          }}
        >
          The home page should open in stillness, not clutter.
        </h1>
      </div>

      <div
        aria-live="polite"
        style={{
          padding: "1rem 1.1rem",
          borderRadius: "18px",
          ...getStartupTruthCardStyle(startupTruthState)
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "1rem",
            flexWrap: "wrap"
          }}
        >
          <div>
            <div
              style={{
                fontSize: "0.78rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: palette.sandstone,
                marginBottom: "0.28rem"
              }}
            >
              Startup truth
            </div>
            <div
              style={{
                fontSize: "1rem",
                fontWeight: 700,
                color: palette.silver
              }}
            >
              {startupTruthMessage}
            </div>
          </div>

          <StatusBadge state={startupSurfaceState} />
        </div>

        <div
          style={{
            marginTop: "0.65rem",
            color: palette.silverMuted,
            lineHeight: 1.58
          }}
        >
          {startupTruthDetail}
        </div>

        <div
          style={{
            display: "flex",
            gap: "0.75rem",
            flexWrap: "wrap",
            marginTop: "0.75rem",
            color: palette.silverMuted,
            fontSize: "0.82rem"
          }}
        >
          {bridgeApiVersion && <span>API {bridgeApiVersion}</span>}
          {bridgeContractVersion && <span>Bridge contract {bridgeContractVersion}</span>}
          {runtimeContractVersion && <span>Runtime contract {runtimeContractVersion}</span>}
          {capabilityContractVersion && (
            <span>Capability contract {capabilityContractVersion}</span>
          )}
          <span>
            {startupReady ? "Not falsely waiting" : "Not ready until truth is known"}
          </span>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: "0.85rem"
        }}
      >
        {[
          {
            title: "Chamber posture",
            tone: palette.teal,
            body: "This home page should orient you calmly before you enter any working room."
          },
          {
            title: "Design posture",
            tone: palette.bronze,
            body: "Decorated, grounded, and serious. Not generic SaaS, not theatrical control-room cosplay."
          },
          {
            title: "Operational honesty",
            tone: palette.emerald,
            body: "Working rooms should only claim what the body can really do right now."
          }
        ].map((card) => (
          <div
            key={card.title}
            style={{
              padding: "1rem",
              borderRadius: "18px",
              border: `1px solid ${palette.lineSilver}`,
              background:
                "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.74) 100%)"
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.55rem",
                marginBottom: "0.55rem"
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: "0.7rem",
                  height: "0.7rem",
                  borderRadius: "999px",
                  background: card.tone,
                  boxShadow: `0 0 14px ${card.tone}`
                }}
              />
              <strong style={{ fontSize: "0.98rem" }}>{card.title}</strong>
            </div>
            <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>{card.body}</div>
          </div>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "0.85rem"
        }}
      >
        {[
          {
            title: "Projects",
            body: "Project chambers, continuity, and project-scoped work live here."
          },
          {
            title: "Conversations",
            body: "The first working room. Speak with Elysia through the local governed path."
          },
          {
            title: "Governance",
            body: "Rules of the house, control states, trust zones, and authority surfaces live here."
          },
          {
            title: "Memory",
            body: "Canonical memory, retrieval, teaching, tiering, backup/restore, and deletion stewardship live here under account and privacy policy."
          }
        ].map((card) => (
          <div
            key={card.title}
            style={{
              padding: "1rem",
              borderRadius: "18px",
              border: `1px solid ${palette.lineSilver}`,
              background:
                "linear-gradient(180deg, rgba(18, 25, 37, 0.70) 0%, rgba(11, 14, 18, 0.76) 100%)"
            }}
          >
            <div
              style={{
                fontSize: "0.82rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: palette.sandstone,
                marginBottom: "0.5rem"
              }}
            >
              {card.title}
            </div>
            <div style={{ color: palette.silverMuted, lineHeight: 1.58 }}>
              {card.body}
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          marginTop: "auto",
          padding: "1rem 1.05rem",
          borderRadius: "18px",
          border: `1px dashed ${startupReady ? "rgba(126, 215, 209, 0.26)" : palette.lineBronze}`,
          background: "rgba(11, 14, 18, 0.42)",
          color: palette.silverMuted,
          lineHeight: 1.6
        }}
      >
        {startupReady
          ? "The chamber is ready. Working rooms can now be entered honestly through the left rail."
          : "The chamber is visible, but readiness is not yet confirmed. Enter working rooms with that truth kept explicit."}
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          alignItems: "center",
          gap: "0.75rem",
          color: palette.silverMuted
        }}
      >
        <span>{state?.active_username ? `Logged in as ${state.active_username}` : "Local session active"}</span>
        <button
          type="button"
          onClick={() => void logout()}
          style={{
            border: `1px solid ${palette.lineSilver}`,
            borderRadius: "12px",
            padding: "0.66rem 0.86rem",
            background: "rgba(11, 14, 18, 0.42)",
            color: palette.silver,
            cursor: "pointer"
          }}
        >
          Log out
        </button>
      </div>
    </div>
  );
}
