import { useEffect, useMemo, useState } from "react";
import {
  fetchCognitionStatus,
  fetchGovernanceState,
  fetchMemoryPendingApprovals,
  fetchResearchEgressApprovals,
  resolveResearchEgressApproval,
  type GovernanceControl,
  type GovernanceStateData,
  type CognitionStatusEnvelope
} from "./api/bridgeClient";
import GovernancePanel from "./GovernancePanel";
import GovernanceControlCard from "./GovernanceControlCard";
import TrustZoneView from "./TrustZoneView";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";

export type GovernancePageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)"
} as const;

const HUMANIZED_VALUE_MAP: Record<string, string> = {
  primary_general: "Primary general",
  approval_governed: "Approval-governed",
  "approval-governed": "Approval-governed",
  policy_governed_session_journaling: "Policy-governed session journaling",
  explicit_local_first_role_governed: "Explicit local-first role governance",
  local_roles_declared_models_installed_not_yet_wired:
    "Roles declared, models installed, not yet wired",
  append_only: "Append-only",
  explicit_only: "Explicit-only",
  local_only: "Local-only",
  open_webui: "Open WebUI",
  not_surfaced: "Not surfaced"
};

function isFailureStatus(status?: string): boolean {
  return status === "error" || status === "blocked" || status === "unavailable";
}

function getEnvelopeMessage(
  payload:
    | {
        message?: string;
        errors?: string[];
        warnings?: string[];
      }
    | undefined,
  fallback: string
): string {
  const message = payload?.message?.trim();
  if (message) {
    return message;
  }

  const error = payload?.errors?.find((value) => typeof value === "string" && value.trim());
  if (error) {
    return error;
  }

  const warning = payload?.warnings?.find(
    (value) => typeof value === "string" && value.trim()
  );
  if (warning) {
    return warning;
  }

  return fallback;
}

function filterControls(
  controls: GovernanceControl[] | undefined,
  categories: string[]
): GovernanceControl[] {
  if (!Array.isArray(controls)) {
    return [];
  }

  return controls.filter((control) => {
    if (!control.category) {
      return false;
    }

    return categories.includes(control.category);
  });
}

function firstNonEmpty(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }

  return null;
}

function sectionSourceLabel(
  controls: GovernanceControl[] | undefined,
  fallback?: string | null
): string | null {
  const labels = new Set<string>();

  for (const control of controls ?? []) {
    const label = control.source?.label?.trim();
    if (label) {
      labels.add(label);
    }
  }

  if (labels.size === 1) {
    return Array.from(labels)[0];
  }

  if (labels.size > 1) {
    return `${labels.size} authority surfaces`;
  }

  return fallback ?? null;
}

function titleCaseWords(value: string): string {
  return value.replace(/\b([a-z])/g, (match) => match.toUpperCase());
}

function humanizeGovernanceText(value?: string | null): string | null {
  if (!value?.trim()) {
    return null;
  }

  const direct = HUMANIZED_VALUE_MAP[value];
  if (direct) {
    return direct;
  }

  const normalized = value.replace(/_/g, " ").replace(/-/g, " ").trim();
  if (!normalized) {
    return null;
  }

  const compact = normalized.replace(/\s+/g, " ");
  return titleCaseWords(compact);
}

function humanizeStateLabel(value?: string | null): string | null {
  const humanized = humanizeGovernanceText(value);
  if (!humanized) {
    return null;
  }

  if (humanized === "Display Only") {
    return "Display-only";
  }

  if (humanized === "Live Editable") {
    return "Live editable";
  }

  return humanized;
}

function shouldSurfaceCanonicalRaw(raw: string): boolean {
  return raw.includes("_") && (raw.length > 24 || raw.split("_").length - 1 >= 3);
}

function buildHumanizedControl(control: GovernanceControl): GovernanceControl {
  const raw = typeof control.value === "string" ? control.value : null;
  const humanized = humanizeGovernanceText(raw);
  const authorityNote =
    raw && humanized && humanized !== raw && shouldSurfaceCanonicalRaw(raw)
      ? firstNonEmpty(control.authority_note, `Canonical value: ${raw}`)
      : control.authority_note;

  return {
    ...control,
    value: humanized ?? control.value,
    authority_note: authorityNote
  };
}

function controlsAllInState(
  controls: GovernanceControl[],
  state: GovernanceControl["state"]
): boolean {
  return controls.length > 0 && controls.every((control) => control.state === state);
}

function isDenseControl(control: GovernanceControl): boolean {
  return (
    control.control_id.startsWith("external_helper_") ||
    control.control_id === "role_optional_specialist" ||
    (control.detail?.length ?? 0) > 220
  );
}

function SummaryCard({
  title,
  value,
  tone
}: {
  title: string;
  value: string;
  tone: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: "0.32rem",
        padding: "0.86rem",
        borderRadius: "16px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.44) 0%, rgba(18, 25, 37, 0.58) 100%)"
      }}
    >
      <div
        style={{
          fontSize: "0.72rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: tone
        }}
      >
        {title}
      </div>
      <div
        style={{
          color: palette.silver,
          fontWeight: 600,
          lineHeight: 1.4,
          wordBreak: "break-word"
        }}
      >
        {value}
      </div>
    </div>
  );
}

function EmptySectionMessage({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: "0.9rem",
        borderRadius: "16px",
        border: `1px dashed ${palette.lineSilver}`,
        background: "rgba(11, 14, 18, 0.42)",
        color: palette.silverMuted,
        lineHeight: 1.55
      }}
    >
      {text}
    </div>
  );
}

function ResponsiveCardGrid({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
        gap: "0.8rem"
      }}
    >
      {children}
    </div>
  );
}

export default function GovernancePage({
  startupReady,
  onRightDrawerSectionsChange
}: GovernancePageProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [governanceData, setGovernanceData] = useState<GovernanceStateData | null>(null);
  const [governanceError, setGovernanceError] = useState<string | null>(null);
  const [cognitionData, setCognitionData] = useState<CognitionStatusEnvelope["data"] | null>(null);
  const [memoryApprovals, setMemoryApprovals] = useState<Array<Record<string, any>>>([]);
  const [researchApprovals, setResearchApprovals] = useState<Array<Record<string, any>>>([]);
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null);
  const [approvalRefresh, setApprovalRefresh] = useState(0);

  const controlStates = governanceData?.control_states ?? [];
  const trustZones = governanceData?.trust_zones ?? [];
  const liveEditableControlCount =
    governanceData?.mutation_summary?.["safe-live-editable-now"] ?? 0;
  const classifiedControlCount = Object.values(
    governanceData?.mutation_summary ?? {}
  ).reduce((total, count) => total + (count ?? 0), 0);

  const localityControls = useMemo(
    () => filterControls(controlStates, ["locality"]).map(buildHumanizedControl),
    [controlStates]
  );

  const memoryJournalingControls = useMemo(
    () =>
      filterControls(controlStates, ["memory", "journaling"]).map(
        buildHumanizedControl
      ),
    [controlStates]
  );

  const approvalControls = useMemo(
    () => filterControls(controlStates, ["approval"]).map(buildHumanizedControl),
    [controlStates]
  );

  const roleAuthorityOverviewControls = useMemo(() => {
    return controlStates
      .filter((control) => {
        return (
          control.control_id === "model_role_runtime_status" ||
          control.control_id === "model_role_default_role" ||
          control.control_id === "model_role_defined_role_count" ||
          control.control_id.startsWith("external_helper_")
        );
      })
      .map(buildHumanizedControl);
  }, [controlStates]);

  const roleAuthorityCoreControls = useMemo(() => {
    return roleAuthorityOverviewControls.filter(
      (control) => !control.control_id.startsWith("external_helper_")
    );
  }, [roleAuthorityOverviewControls]);

  const externalHelperControls = useMemo(() => {
    return roleAuthorityOverviewControls.filter((control) =>
      control.control_id.startsWith("external_helper_")
    );
  }, [roleAuthorityOverviewControls]);

  const declaredRoleControls = useMemo(() => {
    return controlStates
      .filter((control) => control.control_id.startsWith("role_"))
      .map(buildHumanizedControl);
  }, [controlStates]);

  const routingPrincipleControls = useMemo(() => {
    return controlStates
      .filter((control) =>
        control.control_id.startsWith("model_role_routing_principle_")
      )
      .map(buildHumanizedControl);
  }, [controlStates]);

  const privacyDefaultControls = useMemo(() => {
    return controlStates
      .filter((control) =>
        control.control_id.startsWith("model_role_privacy_default_")
      )
      .map(buildHumanizedControl);
  }, [controlStates]);

  const routingPostureControls = useMemo(() => {
    return controlStates
      .filter((control) => control.control_id.startsWith("routing_"))
      .map(buildHumanizedControl);
  }, [controlStates]);

  const trustZoneControls = useMemo(
    () => filterControls(controlStates, ["trust_zones"]),
    [controlStates]
  );

  const hideLocalityStateBadges = useMemo(
    () => controlsAllInState(localityControls, "display_only"),
    [localityControls]
  );

  const hideRoleOverviewStateBadges = useMemo(
    () => controlsAllInState(roleAuthorityCoreControls, "display_only"),
    [roleAuthorityCoreControls]
  );

  const hideDeclaredRoleStateBadges = useMemo(
    () => controlsAllInState(declaredRoleControls, "display_only"),
    [declaredRoleControls]
  );

  const hideRoutingPrincipleStateBadges = useMemo(
    () => controlsAllInState(routingPrincipleControls, "display_only"),
    [routingPrincipleControls]
  );

  const hidePrivacyDefaultStateBadges = useMemo(
    () => controlsAllInState(privacyDefaultControls, "display_only"),
    [privacyDefaultControls]
  );

  const hideRoutingPostureStateBadges = useMemo(
    () => controlsAllInState(routingPostureControls, "display_only"),
    [routingPostureControls]
  );

  const summaryCards = useMemo(() => {
    return [
      {
        title: "Locality posture",
        tone: palette.teal,
        value:
          governanceData?.locality_summary?.local_only_by_default === true
            ? "Local-only by default"
            : governanceData?.locality_summary?.local_only_by_default === false
              ? "Not local-only by default"
              : startupReady
                ? "Not surfaced"
                : "Waiting for startup truth"
      },
      {
        title: "Default role",
        tone: palette.bronze,
        value:
          humanizeGovernanceText(governanceData?.role_authority?.default_role) ??
          (startupReady ? "Not surfaced" : "Waiting for startup truth")
      },
      {
        title: "Approval posture",
        tone: palette.sandstone,
        value:
          humanizeGovernanceText(governanceData?.approval_summary?.approval_mode) ??
          (startupReady ? "Not surfaced" : "Waiting for startup truth")
      },
      {
        title: "Journal posture",
        tone: palette.emerald,
        value:
          humanizeGovernanceText(governanceData?.journaling_summary?.journal_mode) ??
          (startupReady ? "Not surfaced" : "Waiting for startup truth")
      },
      {
        title: "Mutation posture",
        tone: palette.teal,
        value: governanceData?.mutation_contract_version
          ? `${liveEditableControlCount} live editable · ${classifiedControlCount} classified`
          : startupReady
            ? "Contract not surfaced"
            : "Waiting for startup truth"
      }
    ];
  }, [classifiedControlCount, governanceData, liveEditableControlCount, startupReady]);

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    if (!startupReady) {
      return [
        {
          key: "active_context",
          title: "Active Context",
          state: "partial",
          accent: "warm",
          rows: [
            { label: "Room", value: "Governance" },
            { label: "Surface", value: "Governance chamber" },
            { label: "Context source", value: "Waiting for startup truth" }
          ]
        },
        {
          key: "governance_posture",
          title: "Governance Posture",
          state: "planned",
          rows: [
            { label: "Status", value: "Bridge/runtime truth not ready yet" },
            {
              label: "Next step",
              value: "Wait for startup readiness before inspection"
            }
          ]
        },
        {
          key: "governance_glossary",
          title: "Governance Glossary",
          state: "planned",
          rows: [
            { label: "Display-only", value: "Visible truth, not a live room control" },
            { label: "Planned", value: "Surfaced honestly, not wired yet" }
          ]
        }
      ];
    }

    if (isLoading) {
      return [
        {
          key: "active_context",
          title: "Active Context",
          state: "live",
          accent: "warm",
          rows: [
            { label: "Room", value: "Governance" },
            { label: "Surface", value: "Governance chamber" },
            { label: "Context source", value: "Governance room shell state" }
          ]
        },
        {
          key: "governance_posture",
          title: "Current Room Posture",
          state: "partial",
          rows: [
            { label: "Load status", value: "Loading governance state" },
            { label: "Tone", value: "Serious, calm, sovereign" }
          ]
        },
        {
          key: "governance_glossary",
          title: "Governance Glossary",
          state: "partial",
          rows: [
            { label: "Display-only", value: "Visible truth, not a live room control" },
            { label: "Planned", value: "Surfaced honestly, not wired yet" },
            { label: "Inactive", value: "Present, but not currently active" }
          ]
        }
      ];
    }

    if (governanceError) {
      return [
        {
          key: "active_context",
          title: "Active Context",
          state: "live",
          accent: "warm",
          rows: [
            { label: "Room", value: "Governance" },
            { label: "Surface", value: "Governance chamber" },
            { label: "Context source", value: "Governance room shell state" }
          ]
        },
        {
          key: "governance_posture",
          title: "Current Room Posture",
          state: "partial",
          rows: [
            { label: "Load status", value: "Governance state unavailable" },
            { label: "Reason", value: governanceError }
          ]
        },
        {
          key: "source_honesty",
          title: "Source Honesty",
          state: "partial",
          rows: [
            {
              label: "Authority surface",
              value: "Bridge call failed or returned unusable truth"
            },
            {
              label: "Fallback",
              value: "Room remains mounted without fake controls"
            }
          ]
        }
      ];
    }

    return [
      {
        key: "active_context",
        title: "Active Context",
        state: "live",
        accent: "warm",
        rows: [
          { label: "Room", value: "Governance" },
          { label: "Surface", value: "Governance chamber" },
          { label: "Context source", value: "Local bridge governance state" }
        ]
      },
      {
        key: "current_room_posture",
        title: "Current Room Posture",
        state: "partial",
        rows: [
          {
            label: "Locality",
            value:
              governanceData?.locality_summary?.local_only_by_default === true
                ? "Local-only by default"
                : "Not surfaced"
          },
          {
            label: "Default role",
            value:
              humanizeGovernanceText(governanceData?.role_authority?.default_role) ??
              "Not surfaced"
          },
          {
            label: "Approval mode",
            value:
              humanizeGovernanceText(governanceData?.approval_summary?.approval_mode) ??
              "Not surfaced"
          },
          {
            label: "Journal mode",
            value:
              humanizeGovernanceText(governanceData?.journaling_summary?.journal_mode) ??
              "Not surfaced"
          },
          {
            label: "Live-editable controls",
            value: String(liveEditableControlCount)
          },
          {
            label: "Mutation contract",
            value: governanceData?.mutation_contract_version ?? "Not surfaced"
          }
        ]
      },
      {
        key: "authority_surfaces",
        title: "Authority Surfaces",
        state: "partial",
        rows: [
          {
            label: "Role authority",
            value: governanceData?.role_authority?.authority_label ?? "Not surfaced"
          },
          {
            label: "Routing",
            value: governanceData?.routing_summary?.source?.label ?? "Not surfaced"
          },
          {
            label: "Memory / journal",
            value:
              firstNonEmpty(
                governanceData?.memory_summary?.source?.label,
                governanceData?.journaling_summary?.source?.label
              ) ?? "Not surfaced"
          },
          {
            label: "Approval",
            value: governanceData?.approval_summary?.source?.label ?? "Not surfaced"
          }
        ]
      },
      {
        key: "adaptive_cognition",
        title: "Adaptive Cognition",
        state: cognitionData ? (cognitionData.emergency?.active ? "blocked" : "live") : "unavailable",
        accent: cognitionData?.emergency?.active ? "warm" : "teal",
        rows: cognitionData
          ? [
              { label: "Autonomy", value: `Level ${String(cognitionData.effective_controls?.autonomy_level ?? "unknown")}` },
              { label: "Preferred gear", value: humanizeGovernanceText(String(cognitionData.effective_controls?.preferred_reasoning_gear ?? "automatic")) ?? "Automatic" },
              { label: "Compute", value: humanizeGovernanceText(String(cognitionData.effective_controls?.compute_preference ?? "automatic")) ?? "Automatic" },
              { label: "Active jobs", value: String(cognitionData.compute?.active_job_count ?? 0) },
              { label: "GPU leases", value: String(cognitionData.active_gpu_leases?.length ?? 0) },
              { label: "Emergency", value: cognitionData.emergency?.active ? "STOP active" : "Ready" }
            ]
          : [{ label: "Status", value: "Cognition truth unavailable" }]
      },
      {
        key: "governance_glossary",
        title: "Governance Glossary",
        state: "partial",
        rows: [
          { label: "Read-only", value: "Constitutional truth; no mutation contract" },
          { label: "Plan-only", value: "Future exact preview; no apply authority yet" },
          { label: "Profile-gated", value: "Requires an optional profile and proof" },
          { label: "Lab-gated", value: "Requires a bounded Lab contract and stop path" },
          { label: "Hard-prohibited", value: "Cannot be enabled by default or casual UI state" }
        ]
      }
    ];
  }, [
    cognitionData,
    governanceData,
    governanceError,
    isLoading,
    liveEditableControlCount,
    startupReady
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);

    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  useEffect(() => {
    let cancelled = false;

    if (!startupReady) {
      setIsLoading(false);
      setGovernanceError(null);
      setGovernanceData(null);
      setCognitionData(null);

      return () => {
        cancelled = true;
      };
    }

    const loadGovernanceState = async () => {
      setIsLoading(true);
      setGovernanceError(null);

      void fetchCognitionStatus()
        .then((cognitionResult) => {
          if (!cancelled) {
            setCognitionData(cognitionResult.payload?.data ?? null);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setCognitionData(null);
          }
        });

      const [result, pendingResult, researchPendingResult] = await Promise.all([
        fetchGovernanceState(),
        fetchMemoryPendingApprovals(),
        fetchResearchEgressApprovals()
      ]);

      if (cancelled) {
        return;
      }

      const payload = result.payload;
      if (!result.ok || isFailureStatus(payload?.status)) {
        setGovernanceError(
          getEnvelopeMessage(
            payload,
            "Governance could not be loaded from the local bridge."
          )
        );
        setGovernanceData(null);
        setIsLoading(false);
        return;
      }

      setGovernanceData(payload?.data ?? null);
      setMemoryApprovals(
        Array.isArray(pendingResult.payload.data?.approvals)
          ? pendingResult.payload.data.approvals
          : []
      );
      setResearchApprovals(
        Array.isArray(researchPendingResult.payload.data?.approvals)
          ? researchPendingResult.payload.data.approvals as Array<Record<string, any>>
          : []
      );
      setIsLoading(false);
    };

    void loadGovernanceState();

    return () => {
      cancelled = true;
    };
  }, [startupReady, approvalRefresh]);

  async function resolveResearchApproval(approvalId: string, approve: boolean) {
    const result = await resolveResearchEgressApproval(approvalId, approve, approve);
    if (result.ok) {
      setApprovalNotice(
        approve
          ? "Exact research egress approved and the bound initiating search executed once. Its token was consumed server-side and was not exposed."
          : "Research egress denied; no query was sent."
      );
      setApprovalRefresh((value) => value + 1);
    } else {
      setApprovalNotice(getEnvelopeMessage(result.payload, "Research egress approval could not be resolved."));
    }
  }

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.92rem",
        minWidth: 0,
        minHeight: 0,
        height: "100%",
        maxHeight: "100%",
        boxSizing: "border-box",
        overflowY: "auto",
        paddingRight: "0.1rem",
        paddingBottom: "0.08rem"
      }}
    >
      <div style={{ display: "grid", gap: "0.46rem" }}>
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: palette.sandstone
          }}
        >
          Governance
        </div>

        <h1
          style={{
            margin: 0,
            fontSize: "2.02rem",
            lineHeight: 1.08,
            color: palette.silver
          }}
        >
          Rules of the house, surfaced honestly.
        </h1>

        <div
          style={{
            maxWidth: "76ch",
            color: palette.silverMuted,
            lineHeight: 1.62
          }}
        >
          This chamber shows what is in force, where that authority comes from,
          and which surfaces are truly live versus only displayed. Governance is
          not a casual settings page. It is a trust room.
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "0.76rem"
        }}
      >
        {summaryCards.map((card) => (
          <SummaryCard
            key={card.title}
            title={card.title}
            value={card.value}
            tone={card.tone}
          />
        ))}
      </div>

      {!startupReady ? (
        <GovernancePanel
          title="Waiting for startup truth"
          description="The Governance chamber is mounted, but the bridge/runtime trust surfaces are not ready yet."
          note="Do not pretend governance data exists before the local bridge says it does."
          tone="warm"
          stateLabel="Not ready"
        >
          <EmptySectionMessage text="Governance truth has not been fetched yet because startup readiness has not been reached. This room stays honest rather than fabricating empty controls." />
        </GovernancePanel>
      ) : isLoading ? (
        <GovernancePanel
          title="Loading governance state"
          description="The room is querying the local bridge for current authority surfaces and trust posture."
          note="No interactive-looking control should appear before its truth arrives."
          tone="cool"
          stateLabel="Loading"
          sourceLabel="/governance/state"
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: "0.8rem"
            }}
          >
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                style={{
                  height: "118px",
                  borderRadius: "16px",
                  border: `1px solid ${palette.lineSilver}`,
                  background:
                    "linear-gradient(180deg, rgba(24, 33, 48, 0.34) 0%, rgba(18, 25, 37, 0.46) 100%)"
                }}
              />
            ))}
          </div>
        </GovernancePanel>
      ) : governanceError ? (
        <GovernancePanel
          title="Governance state unavailable"
          description="The room remains mounted, but the local bridge did not return a usable governance payload."
          note="A governance-room failure is itself trust-relevant information."
          tone="warm"
          stateLabel="Unavailable"
        >
          <div
            style={{
              padding: "0.95rem",
              borderRadius: "16px",
              border: `1px solid rgba(138, 106, 60, 0.30)`,
              background:
                "linear-gradient(180deg, rgba(43, 31, 21, 0.42) 0%, rgba(18, 25, 37, 0.62) 100%)",
              color: palette.silver,
              lineHeight: 1.58
            }}
          >
            {governanceError}
          </div>
        </GovernancePanel>
      ) : !governanceData ? (
        <GovernancePanel
          title="No governance payload surfaced"
          description="The bridge call completed, but no usable governance data was returned."
          note="This is a room truth problem, not a reason to fake content."
          stateLabel="Empty"
        >
          <EmptySectionMessage text="No governance payload was available to render." />
        </GovernancePanel>
      ) : (
        <>
          <GovernancePanel
            title="Governance mutation contract"
            description="Every surfaced control has an exact mutability class, risk level, and promotion boundary."
            note="Plan, approval, apply, and restore contracts fail closed. Frontend state alone never changes Governance law."
            tone="cool"
            stateLabel={`${liveEditableControlCount} live editable`}
            sourceLabel={
              governanceData.mutation_contract_version ?? "Contract not surfaced"
            }
          >
            <div
              style={{
                display: "grid",
                gap: "0.52rem",
                padding: "0.9rem",
                borderRadius: "16px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(11, 14, 18, 0.42)",
                color: palette.silverMuted,
                lineHeight: 1.55
              }}
            >
              <strong style={{ color: palette.silver }}>
                No current production Governance control is live-editable.
              </strong>
              <span>
                Future powers remain plan-only, profile-gated, or Lab-gated until
                their authoritative adapters, approvals, recovery, doctor proof,
                and tests are real. Silent cloud fallback and ordinary vault access
                remain hard-prohibited by default.
              </span>
              {governanceData.governance_config_hash ? (
                <span>
                  State version: {governanceData.governance_config_hash.slice(0, 12)}
                </span>
              ) : null}
            </div>
          </GovernancePanel>

          <GovernancePanel
            title="Adaptive cognition policy in force"
            description="Read-only, content-free runtime truth for the authenticated profile. User choices remain in Settings; installation ceilings remain in Admin."
            note="The Governor may reduce effort or escalate reasoning, but it cannot raise autonomy, cross privacy boundaries, bypass approvals, or grant an Admin access to user content."
            tone="cool"
            stateLabel={cognitionData?.emergency?.active ? "STOP active" : "Governed and ready"}
            sourceLabel="/cognition/status"
          >
            {cognitionData ? (
              <ResponsiveCardGrid>
                {[
                  ["Autonomy ceiling", `Level ${String(cognitionData.effective_controls?.autonomy_level ?? "unknown")}`],
                  ["Reasoning gears", `${String(cognitionData.reasoning_gears?.length ?? 0)} available · ${humanizeGovernanceText(String(cognitionData.effective_controls?.preferred_reasoning_gear ?? "automatic"))}`],
                  ["Compute policy", `${humanizeGovernanceText(String(cognitionData.effective_controls?.compute_preference ?? "automatic"))} · ${String(cognitionData.compute?.active_job_count ?? 0)} active jobs`],
                  ["Resource ceilings", `CPU ${String(cognitionData.effective_controls?.cpu_percent_ceiling ?? "?")}% · RAM ${String(cognitionData.effective_controls?.ram_mb_ceiling ?? "?")} MiB · VRAM ${String(cognitionData.effective_controls?.vram_mb_ceiling ?? "?")} MiB`],
                  ["GPU leases", String(cognitionData.active_gpu_leases?.length ?? 0)],
                  ["Emergency posture", cognitionData.emergency?.active ? "New work blocked; explicit reset required" : "Stop authority armed"]
                ].map(([label, value]) => (
                  <div key={label} style={{ padding: "0.9rem", borderRadius: "16px", border: `1px solid ${palette.lineSilver}`, color: palette.silverMuted }}>
                    <strong style={{ color: palette.silver, display: "block", marginBottom: "0.28rem" }}>{label}</strong>
                    <span>{value}</span>
                  </div>
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="Cognition policy truth is temporarily unavailable; no status is fabricated." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Locality and external boundaries"
            description="The local bridge and boundary posture should be visible here before any outward power is presumed."
            note={governanceData.locality_summary?.detail ?? null}
            tone="cool"
            stateLabel={humanizeStateLabel(governanceData.locality_summary?.state) ?? null}
            sourceLabel={sectionSourceLabel(
              localityControls,
              governanceData.locality_summary?.source?.label ?? null
            )}
          >
            {localityControls.length > 0 ? (
              <ResponsiveCardGrid>
                {localityControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    showStateBadge={!hideLocalityStateBadges}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="No locality controls were surfaced by the current governance payload." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Role authority overview"
            description="Default role law, runtime role posture, and explicit external-helper status belong here."
            note={governanceData.role_authority?.detail ?? undefined}
            tone="warm"
            stateLabel={firstNonEmpty(
              governanceData.role_authority?.default_role
                ? `Default role: ${humanizeGovernanceText(governanceData.role_authority.default_role)}`
                : null,
              governanceData.role_authority?.authority_label
            )}
            sourceLabel={sectionSourceLabel(
              roleAuthorityOverviewControls,
              governanceData.role_authority?.authority_label ?? null
            )}
          >
            {roleAuthorityCoreControls.length > 0 ? (
              <ResponsiveCardGrid>
                {roleAuthorityCoreControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    showStateBadge={!hideRoleOverviewStateBadges}
                    compact={isDenseControl(control)}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : null}

            {externalHelperControls.length > 0 ? (
              <div
                style={{
                  display: "grid",
                  gap: "0.48rem"
                }}
              >
                <div
                  style={{
                    fontSize: "0.76rem",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: palette.sandstone
                  }}
                >
                  External helpers
                </div>
                <ResponsiveCardGrid>
                  {externalHelperControls.map((control) => (
                    <GovernanceControlCard
                      key={control.control_id}
                      control={control}
                      showCategory={false}
                      showSourcePath={false}
                      compact
                    />
                  ))}
                </ResponsiveCardGrid>
              </div>
            ) : null}

            {!roleAuthorityCoreControls.length && !externalHelperControls.length ? (
              <EmptySectionMessage text="No role-authority overview controls were surfaced by the current governance payload." />
            ) : null}
          </GovernancePanel>

          <GovernancePanel
            title="Declared roles"
            description="These are the currently surfaced role entries and their preferred first-position models."
            note="The chamber should show declared role identity without turning into a raw config dump."
            tone="warm"
            stateLabel={
              declaredRoleControls.length ? `${declaredRoleControls.length} roles surfaced` : null
            }
            sourceLabel={sectionSourceLabel(
              declaredRoleControls,
              governanceData.role_authority?.authority_label ?? null
            )}
          >
            {declaredRoleControls.length > 0 ? (
              <ResponsiveCardGrid>
                {declaredRoleControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    showStateBadge={!hideDeclaredRoleStateBadges}
                    compact={declaredRoleControls.length >= 4 || isDenseControl(control)}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="No declared roles were surfaced by the current governance payload." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Routing principles"
            description="These are the routing-law commitments that define how the system should and should not move between roles or beyond the local core."
            note="Routing principles are constitutional signals, not decorative feature flags."
            tone="cool"
            stateLabel={
              routingPrincipleControls.length
                ? `${routingPrincipleControls.length} principles surfaced`
                : null
            }
            sourceLabel={sectionSourceLabel(routingPrincipleControls)}
          >
            {routingPrincipleControls.length > 0 ? (
              <ResponsiveCardGrid>
                {routingPrincipleControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    showStateBadge={!hideRoutingPrincipleStateBadges}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="No routing principles were surfaced by the current governance payload." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Privacy / trust defaults"
            description="These defaults describe the protective baseline the room should assume before any exceptional routing or boundary crossing is considered."
            note="Privacy and trust defaults should read like house law, not backend variable names."
            tone="cool"
            stateLabel={
              privacyDefaultControls.length
                ? `${privacyDefaultControls.length} defaults surfaced`
                : null
            }
            sourceLabel={sectionSourceLabel(privacyDefaultControls)}
          >
            {privacyDefaultControls.length > 0 ? (
              <ResponsiveCardGrid>
                {privacyDefaultControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    showStateBadge={!hidePrivacyDefaultStateBadges}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="No privacy or trust defaults were surfaced by the current governance payload." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Routing posture"
            description="This is the presently surfaced routing mode and its current downstream posture."
            note={governanceData.routing_summary?.detail ?? undefined}
            tone="cool"
            stateLabel={
              humanizeGovernanceText(governanceData.routing_summary?.routing_mode) ?? null
            }
            sourceLabel={sectionSourceLabel(
              routingPostureControls,
              governanceData.routing_summary?.source?.label ?? null
            )}
          >
            {routingPostureControls.length > 0 ? (
              <ResponsiveCardGrid>
                {routingPostureControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    showStateBadge={!hideRoutingPostureStateBadges}
                    compact={isDenseControl(control)}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="No routing-posture controls were surfaced by the current governance payload." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Pending canonical-memory approvals"
            description="Exact, short-lived consequence previews waiting in the authenticated account scope. Approval tokens are never re-exposed here."
            note="Apply is only possible from the initiating flow that still holds the exact one-time token."
            tone="warm"
            stateLabel={`${memoryApprovals.length} pending`}
            sourceLabel="Canonical Memory Fabric approval ledger"
          >
            {memoryApprovals.length ? (
              <ResponsiveCardGrid>
                {memoryApprovals.map((approval) => (
                  <div key={String(approval.approval_id)} style={{ padding: "0.9rem", borderRadius: "16px", border: `1px solid ${palette.lineSilver}`, color: palette.silverMuted }}>
                    <strong style={{ color: palette.silver }}>{String(approval.action)}</strong>
                    <div>Target: {String(approval.target_id)}</div>
                    <div>Expires: {String(approval.expires_at_utc)}</div>
                    <div>Token exposed: No</div>
                  </div>
                ))}
              </ResponsiveCardGrid>
            ) : <EmptySectionMessage text="No unconsumed memory consequence approvals are pending." />}
          </GovernancePanel>

          <GovernancePanel
            title="Pending research egress approvals"
            description="Sensitive public queries wait here as actor-bound, operation-bound, destination-bound, request-hash-bound, expiring one-time approvals. Sealed content is never eligible."
            note={approvalNotice ?? "Approving does not broaden Internet access and does not expose private context."}
            tone="warm"
            stateLabel={`${researchApprovals.length} pending`}
            sourceLabel="Research egress approval ledger"
          >
            {researchApprovals.length ? (
              <ResponsiveCardGrid>
                {researchApprovals.map((approval) => {
                  const preview = approval.preview && typeof approval.preview === "object" ? approval.preview as Record<string, any> : {};
                  return (
                    <div key={String(approval.approval_id)} style={{ display: "grid", gap: "0.48rem", padding: "0.9rem", borderRadius: "16px", border: `1px solid ${palette.lineSilver}`, color: palette.silverMuted }}>
                      <strong style={{ color: palette.silver }}>{humanizeGovernanceText(String(approval.operation))}</strong>
                      <div>Destination: {humanizeGovernanceText(String(approval.destination_class))}</div>
                      <div>Categories: {Array.isArray(approval.data_categories) ? approval.data_categories.join(", ") : "Sensitive"}</div>
                      <div>Preview: {String(preview.query_preview ?? "Sanitized preview unavailable")}</div>
                      <div>Expires: {String(approval.expires_at)}</div>
                      <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                        <button type="button" onClick={() => void resolveResearchApproval(String(approval.approval_id), true)}>Approve once</button>
                        <button type="button" onClick={() => void resolveResearchApproval(String(approval.approval_id), false)}>Deny</button>
                      </div>
                    </div>
                  );
                })}
              </ResponsiveCardGrid>
            ) : <EmptySectionMessage text="No sensitive research egress approvals are pending." />}
          </GovernancePanel>

          <GovernancePanel
            title="Memory and journaling policy"
            description="Memory posture and journaling truth should be inspectable without pretending everything is already editable."
            note={
              firstNonEmpty(
                governanceData.memory_summary?.detail,
                governanceData.journaling_summary?.detail
              ) ?? undefined
            }
            stateLabel={firstNonEmpty(
              humanizeGovernanceText(governanceData.memory_summary?.retention_posture),
              humanizeGovernanceText(governanceData.journaling_summary?.journal_mode)
            )}
            sourceLabel={sectionSourceLabel(memoryJournalingControls)}
          >
            {memoryJournalingControls.length > 0 ? (
              <ResponsiveCardGrid>
                {memoryJournalingControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    compact={isDenseControl(control)}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="No memory or journaling controls were surfaced by the current governance payload." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Approval levels and bounded action controls"
            description="Risk, destructive actions, and outward behavior should remain governance-visible rather than silently assumed."
            note={governanceData.approval_summary?.detail ?? undefined}
            tone="warm"
            stateLabel={
              humanizeGovernanceText(governanceData.approval_summary?.approval_mode) ?? null
            }
            sourceLabel={sectionSourceLabel(
              approvalControls,
              governanceData.approval_summary?.source?.label ?? null
            )}
          >
            {approvalControls.length > 0 ? (
              <ResponsiveCardGrid>
                {approvalControls.map((control) => (
                  <GovernanceControlCard
                    key={control.control_id}
                    control={control}
                    showCategory={false}
                    showSourcePath={false}
                    compact={isDenseControl(control)}
                  />
                ))}
              </ResponsiveCardGrid>
            ) : (
              <EmptySectionMessage text="No approval controls were surfaced by the current governance payload." />
            )}
          </GovernancePanel>

          <GovernancePanel
            title="Trust zones and vault rules"
            description="Not all parts of the house are equal. Trust zones make access posture, sealing, and boundary structure inspectable."
            note="This is a chamber floor plan, not a fake security console."
            tone="warm"
            stateLabel={trustZones.length ? `${trustZones.length} zones surfaced` : null}
            sourceLabel={
              governanceData.control_sources?.length
                ? `${governanceData.control_sources.length} control sources surfaced`
                : null
            }
          >
            <TrustZoneView zones={trustZones} controls={trustZoneControls} />
          </GovernancePanel>

          <div
            aria-hidden="true"
            style={{
              marginTop: "0.08rem",
              paddingBottom: "0.04rem",
              display: "flex",
              justifyContent: "center"
            }}
          >
            <div
              style={{
                width: "100%",
                borderTop: `1px solid rgba(138, 106, 60, 0.10)`
              }}
            />
          </div>
        </>
      )}
    </div>
  );
}
