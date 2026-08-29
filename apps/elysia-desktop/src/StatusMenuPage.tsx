import { useEffect, useState, type CSSProperties } from "react";
import {
  fetchCognitionStatus,
  fetchDueProspectiveMemory,
  fetchMemoryHealth,
  type BridgeStartupState,
  type CognitionStatusEnvelope
} from "./api/bridgeClient";

type StatusSurfaceState =
  | "live"
  | "partial"
  | "planned"
  | "inactive"
  | "unavailable"
  | "degraded"
  | "blocked";

type StatusMenuPageProps = {
  startupTruthState: BridgeStartupState;
  startupTruthMessage: string;
  startupTruthDetail: string;
  startupReady: boolean;
  bridgeApiVersion?: string;
  bridgeContractVersion?: string;
  runtimeContractVersion?: string;
  capabilityContractVersion?: string;

  localCoreState?: StatusSurfaceState;
  localCoreValue?: string;
  approvalNeededState?: StatusSurfaceState;
  approvalNeededValue?: string;
  blockedPathsState?: StatusSurfaceState;
  blockedPathsValue?: string;
  externalBoundaryState?: StatusSurfaceState;
  externalBoundaryValue?: string;

  activeRoleState?: StatusSurfaceState;
  activeRoleValue?: string;
  runtimeTagState?: StatusSurfaceState;
  runtimeTagValue?: string;
  fallbackState?: StatusSurfaceState;
  fallbackValue?: string;
  memoryState?: StatusSurfaceState;
  memoryValue?: string;
  sandboxState?: StatusSurfaceState;
  sandboxValue?: string;
  outwardBoundaryState?: StatusSurfaceState;
  outwardBoundaryValue?: string;
};

type StatusCard = {
  title: string;
  state: StatusSurfaceState;
  value: string;
  explanation: string;
};

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
  lineTeal: "rgba(126, 215, 209, 0.22)",
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

function StatusSummaryCard({ card }: { card: StatusCard }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.65rem",
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
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "0.75rem"
        }}
      >
        <div
          style={{
            fontSize: "0.8rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.sandstone
          }}
        >
          {card.title}
        </div>
        <StatusBadge state={card.state} />
      </div>

      <div
        style={{
          fontSize: "1rem",
          fontWeight: 700,
          color: palette.silver,
          lineHeight: 1.25
        }}
      >
        {card.value}
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.55,
          fontSize: "0.88rem"
        }}
      >
        {card.explanation}
      </div>
    </div>
  );
}

function DetailRow({
  label,
  state,
  value,
  explanation
}: {
  label: string;
  state: StatusSurfaceState;
  value: string;
  explanation: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(140px, 180px) minmax(0, 1fr) auto",
        gap: "0.85rem",
        alignItems: "start",
        padding: "0.9rem 0",
        borderTop: `1px solid ${palette.lineSilver}`
      }}
    >
      <div
        style={{
          fontSize: "0.82rem",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: palette.sandstone
        }}
      >
        {label}
      </div>

      <div style={{ display: "grid", gap: "0.28rem", minWidth: 0 }}>
        <div
          style={{
            color: palette.silver,
            fontSize: "0.96rem",
            fontWeight: 600,
            lineHeight: 1.35
          }}
        >
          {value}
        </div>
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.5,
            fontSize: "0.86rem"
          }}
        >
          {explanation}
        </div>
      </div>

      <StatusBadge state={state} />
    </div>
  );
}

function GlossaryCard({
  state,
  meaning
}: {
  state: StatusSurfaceState;
  meaning: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: "0.6rem",
        padding: "0.95rem",
        borderRadius: "16px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.70) 0%, rgba(11, 14, 18, 0.76) 100%)"
      }}
    >
      <StatusBadge state={state} />
      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.55,
          fontSize: "0.86rem"
        }}
      >
        {meaning}
      </div>
    </div>
  );
}

export default function StatusMenuPage({
  startupTruthState,
  startupTruthMessage,
  startupTruthDetail,
  startupReady,
  bridgeApiVersion,
  bridgeContractVersion,
  runtimeContractVersion,
  capabilityContractVersion,

  localCoreState,
  localCoreValue,
  approvalNeededState = "inactive",
  approvalNeededValue = "No approval is required for the current chamber state.",
  blockedPathsState = "inactive",
  blockedPathsValue = "No blocked path is active for the current chamber state.",
  externalBoundaryState = "live",
  externalBoundaryValue = "No outward path is active for the current chamber state.",

  activeRoleState = "inactive",
  activeRoleValue = "No active request role is surfaced for the current chamber state.",
  runtimeTagState = "inactive",
  runtimeTagValue = "No active request runtime is surfaced for the current chamber state.",
  fallbackState = "inactive",
  fallbackValue = "No fallback event is active for the current chamber state.",
  memoryState = "live",
  memoryValue = "Canonical memory and governed cognition truth are available through Memory, Health, Requests, Governance, and the active chamber context.",
  sandboxState = "planned",
  sandboxValue = "Sandbox state is not yet fully exposed in this page.",
  outwardBoundaryState = "live",
  outwardBoundaryValue = "Current chamber state remains inside the local boundary."
}: StatusMenuPageProps) {
  const [cognition, setCognition] = useState<CognitionStatusEnvelope["data"] | null>(null);
  const [memoryHealth, setMemoryHealth] = useState<Record<string, any> | null>(null);
  const [prospective, setProspective] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    let active = true;
    async function refreshRuntimeTruth() {
      const [cognitionResult, memoryResult, prospectiveResult] = await Promise.all([
        fetchCognitionStatus(),
        fetchMemoryHealth(),
        fetchDueProspectiveMemory(168)
      ]);
      if (!active) return;
      if (cognitionResult.ok) setCognition(cognitionResult.payload.data ?? null);
      if (memoryResult.ok) {
        setMemoryHealth(
          (memoryResult.payload.data?.health as Record<string, any> | undefined) ?? null
        );
      }
      if (prospectiveResult.ok) {
        setProspective(
          (prospectiveResult.payload.data?.prospective as Record<string, any> | undefined) ?? null
        );
      }
    }
    void refreshRuntimeTruth();
    const timer = window.setInterval(() => void refreshRuntimeTruth(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const resolvedLocalCoreState =
    localCoreState ?? mapStartupTruthToSurfaceState(startupTruthState);
  const resolvedLocalCoreValue =
    localCoreValue ??
    (startupReady ? "Local core verified for current chamber session." : startupTruthMessage);
  const releaseClosure = memoryHealth?.release_closure as Record<string, any> | undefined;
  const lifecycleReady =
    releaseClosure?.canonical_writer_count === 1 &&
    releaseClosure?.object_store?.state === "ready" &&
    releaseClosure?.graph?.state === "ready";
  const resolvedMemoryState: StatusSurfaceState = memoryHealth
    ? lifecycleReady
      ? "live"
      : "degraded"
    : memoryState;
  const resolvedMemoryValue = memoryHealth
    ? `Canonical writers ${String(releaseClosure?.canonical_writer_count ?? "unknown")} · object store ${String(releaseClosure?.object_store?.state ?? "unknown")} · graph ${String(releaseClosure?.graph?.state ?? "unknown")}`
    : memoryValue;
  const dueCount = Number(prospective?.due_count ?? 0);
  const overdueCount = Array.isArray(prospective?.due)
    ? prospective.due.filter((item: Record<string, any>) => item.overdue === true).length
    : 0;

  const currentStateCards: StatusCard[] = [
    {
      title: "Local Core",
      state: resolvedLocalCoreState,
      value: resolvedLocalCoreValue,
      explanation:
        "This reflects whether the current chamber posture is operating inside the local governed path rather than pretending remote readiness."
    },
    {
      title: "Approval State",
      state: approvalNeededState,
      value: approvalNeededValue,
      explanation:
        "This reflects whether a current request is waiting for approval, actively gated, or not currently gated at all."
    },
    {
      title: "Blocked State",
      state: blockedPathsState,
      value: blockedPathsValue,
      explanation:
        "This reflects whether any current chamber or request path is actively blocked right now. It is not the same as the house rule that blocked paths should be shown honestly when they occur."
    },
    {
      title: "External State",
      state: externalBoundaryState,
      value: externalBoundaryValue,
      explanation:
        "This reflects whether the current chamber state is staying local, sealed, or actively using an outward path right now."
    },
    {
      title: "Adaptive Cognition",
      state: cognition?.governor_contract ? "live" : "unavailable",
      value: cognition
        ? `Level ${String(cognition.effective_controls?.autonomy_level ?? "unknown")} · ${String(cognition.effective_controls?.preferred_reasoning_gear ?? "automatic")} gear`
        : "Cognition truth unavailable",
      explanation:
        "The active account's effective autonomy ceiling and reasoning-depth preference come from the governed cognition endpoint; individual requests may select or escalate a different bounded gear."
    },
    {
      title: "Compute / Emergency",
      state: cognition?.emergency?.active ? "blocked" : cognition?.compute ? "live" : "unavailable",
      value: cognition?.emergency?.active
        ? "STOP active — explicit recovery required"
        : cognition
          ? `${String(cognition.compute?.active_job_count ?? 0)} jobs · ${String(cognition.active_gpu_leases?.length ?? 0)} GPU leases`
          : "Compute truth unavailable",
      explanation:
        "Shows bounded queue/lease and system-stop truth without exposing prompts, private content, credentials, or hidden reasoning."
    },
    {
      title: "Prospective reminders",
      state: prospective
        ? prospective.enabled === false
          ? "inactive"
          : dueCount > 0
            ? "live"
            : "inactive"
        : "unavailable",
      value: prospective
        ? prospective.enabled === false
          ? "Local prospective notifications are disabled by the account owner."
          : `${String(dueCount)} due in the next 7 days · ${String(overdueCount)} overdue · Sealed excluded`
        : "Prospective reminder truth unavailable",
      explanation:
        "This authenticated in-app notification count is rebuilt from canonical prospective memory after restart. Sealed content and external delivery are excluded."
    }
  ];

  const runtimeDetailRows: Array<{
    label: string;
    state: StatusSurfaceState;
    value: string;
    explanation: string;
  }> = [
    {
      label: "Current / recent role",
      state: activeRoleState,
      value: activeRoleValue,
      explanation:
        "This shows a current or most-recent role only when the runtime or invoker endpoint provides it; absence is not filled with a configured default."
    },
    {
      label: "Current / recent runtime",
      state: runtimeTagState,
      value: runtimeTagValue,
      explanation:
        "This shows a current or most-recent runtime/model tag only when the runtime or invoker endpoint provides it."
    },
    {
      label: "Fallback",
      state: fallbackState,
      value: fallbackValue,
      explanation:
        "This indicates whether fallback was actually used for the present chamber/request state rather than merely existing as a possible doctrine."
    },
    {
      label: "Memory",
      state: resolvedMemoryState,
      value: resolvedMemoryValue,
      explanation:
        "This live endpoint truth summarizes the canonical writer and derived object/graph lifecycle without exposing memory content."
    },
    {
      label: "Sandbox",
      state: sandboxState,
      value: sandboxValue,
      explanation:
        "General local sandbox readiness remains planned until profile resolution and doctor/isolation proof exist."
    },
    {
      label: "Outward boundary",
      state: outwardBoundaryState,
      value: outwardBoundaryValue,
      explanation:
        "This indicates whether outward movement is presently sealed, governed, degraded, blocked, or otherwise active in the current chamber state."
    },
    {
      label: "Reasoning gear",
      state: cognition?.governor_contract ? "live" : "unavailable",
      value: cognition
        ? `${String(cognition.reasoning_gears?.length ?? 0)} available · ${String(cognition.effective_controls?.preferred_reasoning_gear ?? "automatic")} preference`
        : "Cognition endpoint unavailable",
      explanation:
        "The current request's selected gear appears in its Request receipt and Conversation drawer; idle status truthfully shows the persisted preference."
    },
    {
      label: "Retrieval / Internet",
      state: cognition ? "live" : "unavailable",
      value: cognition
        ? `${String(cognition.effective_controls?.retrieval_breadth ?? "unknown")} retrieval · Internet ${cognition.effective_controls?.internet_master_enabled ? "ON" : "OFF"}`
        : "Account policy unavailable",
      explanation:
        "Effective account and managed-profile policy is applied before retrieval ranking or any outward research action."
    },
    {
      label: "Compute device / queue",
      state: cognition?.compute ? "live" : "unavailable",
      value: cognition
        ? `${cognition.compute?.gpu?.available ? "GPU available through leases" : "CPU fallback"} · ${String(cognition.compute?.active_job_count ?? 0)} active jobs`
        : "Compute endpoint unavailable",
      explanation:
        "GPU availability never grants a permanent reservation; workload descriptors, ceilings, queue state, and higher-priority work control placement."
    },
    {
      label: "Emergency posture",
      state: cognition?.emergency?.active ? "blocked" : cognition ? "live" : "unavailable",
      value: cognition?.emergency?.active
        ? "STOP active; Owner/Admin resume required"
        : "Stop authority armed",
      explanation:
        "Stop cancels governed work and forces Internet OFF while preserving canonical user data and durable preferences."
    }
  ];

  const glossaryItems: Array<{ state: StatusSurfaceState; meaning: string }> = [
    {
      state: "live",
      meaning:
        "A real source is available now and this surface is presenting current truth rather than placeholder language."
    },
    {
      state: "partial",
      meaning:
        "Some real source exists, but the surface is not yet fully mature, fully wired, or richly surfaced."
    },
    {
      state: "planned",
      meaning:
        "The surface belongs in the architecture, but no real source is yet connected strongly enough to present as live."
    },
    {
      state: "blocked",
      meaning:
        "A boundary, refusal, or permission gate is actively preventing continuation or outward movement."
    },
    {
      state: "degraded",
      meaning:
        "The surface still functions in some form, but truth or capability is reduced compared with the intended healthy path."
    },
    {
      state: "unavailable",
      meaning:
        "The source or service is not currently reachable or cannot honestly provide the expected truth."
    }
  ];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        paddingRight: "0.15rem",
        paddingBottom: "0.35rem"
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
          Status Menu
        </div>
        <h1
          style={{
            margin: 0,
            fontSize: "2.15rem",
            lineHeight: 1.1
          }}
        >
          Expanded trust surfaces for the current chamber state.
        </h1>
        <div
          style={{
            marginTop: "0.55rem",
            color: palette.silverMuted,
            lineHeight: 1.6,
            maxWidth: "78ch"
          }}
        >
          The bottom bar gives the short version. This page gives the expanded
          version: current trust posture, runtime condition, and the meaning of the
          chamber’s compact status language without bloating the shell.
        </div>
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

          <StatusBadge state={mapStartupTruthToSurfaceState(startupTruthState)} />
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
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: "0.85rem"
        }}
      >
        {currentStateCards.map((card) => (
          <StatusSummaryCard key={card.title} card={card} />
        ))}
      </div>

      <div
        style={{
          padding: "1rem 1.05rem",
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
            marginBottom: "0.2rem"
          }}
        >
          House doctrine
        </div>
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.6,
            maxWidth: "78ch"
          }}
        >
          Approval gates, blocked-path honesty, and outward sealing are structural
          rules of this chamber. They are not the same thing as approval being
          required right now, a path being blocked right now, or an outward route
          being active right now.
        </div>
      </div>

      <div
        style={{
          padding: "1rem 1.05rem",
          borderRadius: "18px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.74) 100%)"
        }}
      >
        <div
          style={{
            fontSize: "0.82rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.teal,
            marginBottom: "0.2rem"
          }}
        >
          Runtime trust details
        </div>
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.55,
            marginBottom: "0.4rem"
          }}
        >
          These rows expand the compact bottom-bar trust language into more
          inspectable present-state meaning. In idle chamber state, they should
          remain calm rather than pretending an active request already exists.
        </div>

        <div style={{ display: "grid" }}>
          {runtimeDetailRows.map((row) => (
            <DetailRow
              key={row.label}
              label={row.label}
              state={row.state}
              value={row.value}
              explanation={row.explanation}
            />
          ))}
        </div>
      </div>

      <div
        style={{
          padding: "1rem 1.05rem",
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
            marginBottom: "0.2rem"
          }}
        >
          Trust-language glossary
        </div>
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.55,
            marginBottom: "0.75rem",
            maxWidth: "74ch"
          }}
        >
          This page should explain the shell’s status language plainly, so current
          truth is readable without forcing the bottom bar itself to become crowded
          or verbose.
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            gap: "0.85rem"
          }}
        >
          {glossaryItems.map((item) => (
            <GlossaryCard
              key={item.state}
              state={item.state}
              meaning={item.meaning}
            />
          ))}
        </div>
      </div>

      <div
        style={{
          padding: "1rem 1.05rem",
          borderRadius: "18px",
          border: `1px dashed ${startupReady ? palette.lineTeal : palette.lineBronze}`,
          background: "rgba(11, 14, 18, 0.42)",
          color: palette.silverMuted,
          lineHeight: 1.6
        }}
      >
        The Status Menu should remain distinct from Chamber and Governance. Chamber
        explains what this place is. Governance shows the policy and authority now in
        force, while Settings contains real user controls. Status Menu exists to show
        what condition the chamber is in right now.
      </div>
    </div>
  );
}
