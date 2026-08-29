import { useEffect, useMemo, useState } from "react";
import {
  fetchBridgeHealth,
  fetchCognitionStatus,
  fetchInstallDoctorStatus,
  fetchInstallProfileStatus,
  fetchMemoryHealth,
  type BridgeHealthEnvelope,
  type CognitionStatusEnvelope,
  type HealthSubsystemEntry,
  type InstallDoctorStatusEnvelope,
  type InstallProfileStatusEnvelope
} from "./api/bridgeClient";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";
import ApplicationLifecyclePanel from "./ApplicationLifecyclePanel";

type HealthPageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
};

type LoadState = "idle" | "loading" | "loaded" | "error";

type HealthSurfaceState =
  | "healthy"
  | "degraded"
  | "unhealthy"
  | "unavailable"
  | "unknown"
  | "not_ready"
  | "ready"
  | "warming";

type SubsystemKey =
  | "api"
  | "runtime"
  | "ollama"
  | "searxng"
  | "config"
  | "logging"
  | "journaling"
  | "memory";

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
  lineTeal: "rgba(126, 215, 209, 0.24)",
  panel: "rgba(18, 25, 37, 0.78)",
  panelInset: "rgba(11, 14, 18, 0.62)"
} as const;

const subsystemOrder: Array<{
  key: SubsystemKey;
  label: string;
  description: string;
}> = [
  {
    key: "api",
    label: "Local API",
    description: "Local bridge health surface and route reachability."
  },
  {
    key: "runtime",
    label: "Runtime",
    description: "Core runtime import and expected runtime shape."
  },
  {
    key: "ollama",
    label: "Ollama",
    description: "Local model service reachability on loopback."
  },
  {
    key: "searxng",
    label: "SearXNG",
    description: "Loopback SearXNG reachability without sending a search query."
  },
  {
    key: "config",
    label: "Config",
    description: "Required local config sources can be loaded."
  },
  {
    key: "logging",
    label: "Logging",
    description: "Runtime logging path is writable enough for governed use."
  },
  {
    key: "journaling",
    label: "Journaling",
    description: "Session journal path is writable enough for governed use."
  },
  {
    key: "memory",
    label: "Memory path",
    description: "Local memory path is available enough for normal use."
  }
];

function normalizeState(value?: string | null): HealthSurfaceState {
  const normalized = value?.trim().toLowerCase();

  if (
    normalized === "healthy" ||
    normalized === "degraded" ||
    normalized === "unhealthy" ||
    normalized === "unavailable" ||
    normalized === "unknown" ||
    normalized === "not_ready" ||
    normalized === "ready" ||
    normalized === "warming"
  ) {
    return normalized;
  }

  return "unknown";
}

function humanize(value?: string | null): string {
  if (!value?.trim()) {
    return "Not surfaced";
  }

  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function stateColors(state: HealthSurfaceState) {
  switch (state) {
    case "healthy":
    case "ready":
      return {
        label: state === "ready" ? "Ready" : "Healthy",
        color: palette.teal,
        border: "rgba(126, 215, 209, 0.30)",
        background: "rgba(126, 215, 209, 0.08)"
      };
    case "degraded":
    case "warming":
      return {
        label: state === "warming" ? "Warming" : "Degraded",
        color: palette.sandstone,
        border: "rgba(184, 162, 123, 0.34)",
        background: "rgba(184, 162, 123, 0.10)"
      };
    case "unhealthy":
    case "not_ready":
      return {
        label: state === "not_ready" ? "Not ready" : "Unhealthy",
        color: "#D7A97E",
        border: "rgba(215, 169, 126, 0.34)",
        background: "rgba(215, 169, 126, 0.09)"
      };
    case "unavailable":
      return {
        label: "Unavailable",
        color: "#D8A5A5",
        border: "rgba(216, 165, 165, 0.34)",
        background: "rgba(216, 165, 165, 0.08)"
      };
    case "unknown":
    default:
      return {
        label: "Unknown",
        color: palette.silverMuted,
        border: "rgba(199, 210, 218, 0.20)",
        background: "rgba(199, 210, 218, 0.06)"
      };
  }
}

function drawerStateForHealth(state: HealthSurfaceState): DrawerSection["state"] {
  switch (state) {
    case "healthy":
    case "ready":
      return "live";
    case "degraded":
    case "warming":
    case "unhealthy":
    case "not_ready":
      return "degraded";
    case "unavailable":
      return "unavailable";
    case "unknown":
    default:
      return "partial";
  }
}

function StatusBadge({ state }: { state: HealthSurfaceState }) {
  const colors = stateColors(state);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "max-content",
        padding: "0.24rem 0.58rem",
        borderRadius: "999px",
        border: `1px solid ${colors.border}`,
        background: colors.background,
        color: colors.color,
        fontSize: "0.7rem",
        fontWeight: 700,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        whiteSpace: "nowrap"
      }}
    >
      {colors.label}
    </span>
  );
}

function formatBoolean(value?: boolean | null): string {
  if (value === true) {
    return "Yes";
  }

  if (value === false) {
    return "No";
  }

  return "Not surfaced";
}

function formatDateTime(value?: string | null): string {
  if (!value?.trim()) {
    return "Not surfaced";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const value of values) {
    const trimmed = value?.trim();
    if (!trimmed || seen.has(trimmed)) {
      continue;
    }

    seen.add(trimmed);
    result.push(trimmed);
  }

  return result;
}

function safePercent(numerator: number, denominator: number): number {
  if (denominator <= 0) {
    return 0;
  }

  return Math.round((numerator / denominator) * 100);
}

function ProgressBar({
  label,
  percent,
  detail
}: {
  label: string;
  percent: number;
  detail: string;
}) {
  const boundedPercent = Math.max(0, Math.min(100, percent));

  return (
    <div
      style={{
        display: "grid",
        gap: "0.45rem",
        padding: "0.92rem",
        borderRadius: "16px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.54) 0%, rgba(18, 25, 37, 0.66) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.75rem",
          alignItems: "baseline"
        }}
      >
        <strong style={{ color: palette.silver }}>{label}</strong>
        <span style={{ color: palette.teal, fontWeight: 700 }}>
          {boundedPercent}%
        </span>
      </div>

      <div
        aria-hidden="true"
        style={{
          height: "0.52rem",
          borderRadius: "999px",
          border: `1px solid ${palette.lineSilver}`,
          background: "rgba(11, 14, 18, 0.58)",
          overflow: "hidden"
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${boundedPercent}%`,
            borderRadius: "999px",
            background:
              "linear-gradient(90deg, rgba(126, 215, 209, 0.72) 0%, rgba(47, 138, 104, 0.84) 100%)"
          }}
        />
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.46,
          fontSize: "0.84rem"
        }}
      >
        {detail}
      </div>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  state,
  detail
}: {
  title: string;
  value: string;
  state: HealthSurfaceState;
  detail: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: "0.55rem",
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.62) 0%, rgba(18, 25, 37, 0.74) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.75rem",
          alignItems: "flex-start"
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
          {title}
        </div>
        <StatusBadge state={state} />
      </div>

      <div
        style={{
          color: palette.silver,
          fontWeight: 700,
          fontSize: "1.02rem",
          lineHeight: 1.35
        }}
      >
        {value}
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.5,
          fontSize: "0.88rem"
        }}
      >
        {detail}
      </div>
    </div>
  );
}

function SubsystemCard({
  label,
  description,
  entry
}: {
  label: string;
  description: string;
  entry?: HealthSubsystemEntry | null;
}) {
  const state = normalizeState(entry?.state);
  const note = entry?.note?.trim();

  return (
    <div
      style={{
        display: "grid",
        gap: "0.56rem",
        padding: "0.95rem",
        borderRadius: "17px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.74) 0%, rgba(11, 14, 18, 0.78) 100%)"
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
        <div style={{ display: "grid", gap: "0.18rem" }}>
          <strong style={{ color: palette.silver }}>{label}</strong>
          <span
            style={{
              color: palette.silverMuted,
              fontSize: "0.8rem",
              lineHeight: 1.38
            }}
          >
            {description}
          </span>
        </div>

        <StatusBadge state={state} />
      </div>

      <div
        style={{
          color: palette.teal,
          fontWeight: 700
        }}
      >
        Healthy: {formatBoolean(entry?.healthy)}
      </div>

      <div
        style={{
          minHeight: "2.6rem",
          color: palette.silverMuted,
          lineHeight: 1.48,
          fontSize: "0.86rem"
        }}
      >
        {note || "No subsystem note returned by the health endpoint."}
      </div>
    </div>
  );
}

function HealthNoteList({
  title,
  notes,
  tone = "warm"
}: {
  title: string;
  notes: string[];
  tone?: "warm" | "cool";
}) {
  return (
    <section
      style={{
        display: "grid",
        gap: "0.72rem",
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${tone === "cool" ? palette.lineTeal : palette.lineBronze}`,
        background:
          tone === "cool"
            ? "linear-gradient(180deg, rgba(16, 41, 43, 0.34) 0%, rgba(18, 25, 37, 0.70) 100%)"
            : "linear-gradient(180deg, rgba(43, 31, 21, 0.38) 0%, rgba(18, 25, 37, 0.70) 100%)"
      }}
    >
      <div
        style={{
          fontSize: "0.82rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: tone === "cool" ? palette.teal : palette.bronze
        }}
      >
        {title}
      </div>

      {notes.length > 0 ? (
        <ul
          style={{
            margin: 0,
            paddingLeft: "1.15rem",
            color: palette.silverMuted,
            lineHeight: 1.55
          }}
        >
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : (
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.55
          }}
        >
          No {title.toLowerCase()} were returned by the health endpoint.
        </div>
      )}
    </section>
  );
}

export default function HealthPage({
  startupReady,
  onRightDrawerSectionsChange
}: HealthPageProps) {
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [healthEnvelope, setHealthEnvelope] =
    useState<BridgeHealthEnvelope | null>(null);
  const [profileEnvelope, setProfileEnvelope] =
    useState<InstallProfileStatusEnvelope | null>(null);
  const [doctorEnvelope, setDoctorEnvelope] =
    useState<InstallDoctorStatusEnvelope | null>(null);
  const [cognitionHealth, setCognitionHealth] = useState<Record<string, any> | null>(null);
  const [cognitionEnvelope, setCognitionEnvelope] =
    useState<CognitionStatusEnvelope | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshIndex, setRefreshIndex] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      setLoadState("loading");
      setLoadError(null);

      const [result, profileResult, doctorResult, memoryHealthResult, cognitionResult] = await Promise.all([
        fetchBridgeHealth(),
        fetchInstallProfileStatus().catch(() => null),
        fetchInstallDoctorStatus().catch(() => null),
        fetchMemoryHealth().catch(() => null),
        fetchCognitionStatus().catch(() => null)
      ]);

      if (cancelled) {
        return;
      }

      const payload = result.payload;
      setHealthEnvelope(payload);
      setProfileEnvelope(profileResult?.payload ?? null);
      setDoctorEnvelope(doctorResult?.payload ?? null);
      setCognitionEnvelope(cognitionResult?.payload ?? null);
      setCognitionHealth(
        memoryHealthResult?.ok
          ? memoryHealthResult.payload.data?.health as Record<string, any> ?? null
          : null
      );

      const errors = payload.errors ?? [];
      const firstError = errors.find((value) => value.trim());

      if (!result.ok || payload.status === "error") {
        setLoadState("error");
        setLoadError(
          firstError ??
            "Health endpoint did not return usable local bridge truth."
        );
        return;
      }

      setLoadState("loaded");
      setLoadError(null);
    }

    void loadHealth();

    return () => {
      cancelled = true;
    };
  }, [refreshIndex]);

  const data = healthEnvelope?.data ?? null;
  const profileData = profileEnvelope?.data ?? null;
  const doctorData = doctorEnvelope?.data ?? null;
  const cognitionData = cognitionEnvelope?.data ?? null;
  const effectiveControls = cognitionData?.effective_controls ?? {};
  const computeTruth = cognitionData?.compute ?? {};
  const gpuDevices = Array.isArray(computeTruth?.gpu?.devices) ? computeTruth.gpu.devices : [];
  const modelRows = Array.isArray(cognitionData?.model_registry?.models)
    ? cognitionData.model_registry.models
    : [];
  const healthState = normalizeState(data?.health_state);
  const startupState = normalizeState(data?.startup_state);
  const subsystemEntries = data?.subsystems ?? {};

  const subsystemList = useMemo(() => {
    return subsystemOrder.map((item) => ({
      ...item,
      entry: subsystemEntries[item.key]
    }));
  }, [subsystemEntries]);

  const subsystemCount = subsystemList.length;
  const healthySubsystemCount = subsystemList.filter(
    (item) => item.entry?.healthy === true
  ).length;

  const subsystemReadinessPercent = safePercent(
    healthySubsystemCount,
    subsystemCount
  );

  const coreBooleans = [
    data?.api_reachable,
    data?.runtime_reachable,
    data?.ollama_reachable,
    data?.config_loadable
  ];
  const coreReadyCount = coreBooleans.filter((value) => value === true).length;
  const coreReadinessPercent = safePercent(coreReadyCount, coreBooleans.length);

  const writableBooleans = [
    data?.logging_writable,
    data?.journaling_writable,
    data?.memory_path_available
  ];
  const writableReadyCount = writableBooleans.filter(
    (value) => value === true
  ).length;
  const writableReadinessPercent = safePercent(
    writableReadyCount,
    writableBooleans.length
  );

  const warningNotes = uniqueStrings([
    ...(healthEnvelope?.warnings ?? []),
    ...(data?.health_notes ?? [])
  ]);
  const errorNotes = uniqueStrings([
    ...(healthEnvelope?.errors ?? []),
    ...(profileEnvelope?.errors ?? []),
    ...(doctorEnvelope?.errors ?? []),
    loadError
  ]);
  const profileWarnings = uniqueStrings(profileEnvelope?.warnings ?? []);
  const activeProfile = profileData?.available_profiles?.find(
    (profile) => profile.profile_id === profileData.active_profile_id
  );
  const profileState: HealthSurfaceState =
    profileEnvelope?.status === "error" ||
    profileEnvelope?.status === "unavailable"
      ? "unavailable"
      : profileEnvelope?.status === "degraded" ||
          profileData?.resolution_state === "invalid"
        ? "degraded"
        : profileData?.resolution_state === "resolved"
          ? "ready"
          : "unknown";
  const presentDependencies = profileData?.dependency_summary?.present ?? 0;
  const missingDependencies = profileData?.dependency_summary?.missing ?? 0;
  const optionalMissingDependencies =
    profileData?.dependency_summary?.optional_missing ?? 0;
  const gatedDependencies =
    (profileData?.dependency_summary?.profile_gated ?? 0) +
    (profileData?.dependency_summary?.lab_gated ?? 0);
  const enabledWorkers = (profileData?.worker_summaries ?? []).filter(
    (worker) => worker.enabled
  ).length;
  const doctorState: HealthSurfaceState =
    doctorEnvelope?.status === "error" || doctorEnvelope?.status === "unavailable"
      ? "unavailable"
      : doctorData?.core_ready === true
        ? "ready"
        : doctorData?.overall_status === "degraded"
          ? "degraded"
          : "unknown";

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    const drawerState =
      loadState === "error" ? "unavailable" : drawerStateForHealth(healthState);

    return [
      {
        key: "active_context",
        title: "Active Context",
        state: drawerState,
        accent: "warm",
        rows: [
          { label: "Room", value: "Health" },
          { label: "Surface", value: "Operator health room" },
          {
            label: "Context source",
            value: "/status/health + /status/profiles + /status/doctor"
          }
        ]
      },
      {
        key: "health_summary",
        title: "Health Summary",
        state: drawerState,
        rows: [
          { label: "Overall", value: humanize(data?.health_state) },
          { label: "Startup", value: humanize(data?.startup_state) },
          {
            label: "Healthy subsystems",
            value: `${healthySubsystemCount}/${subsystemCount}`
          },
          {
            label: "Last check",
            value: formatDateTime(data?.last_health_check_utc)
          }
        ]
      },
      {
        key: "health_subsystems",
        title: "Subsystems",
        state: drawerState,
        rows: [
          { label: "API", value: formatBoolean(data?.api_reachable) },
          { label: "Runtime", value: formatBoolean(data?.runtime_reachable) },
          { label: "Ollama", value: formatBoolean(data?.ollama_reachable) },
          { label: "Config", value: formatBoolean(data?.config_loadable) }
        ]
      },
      {
        key: "profile_readiness",
        title: "Profile Readiness",
        state: drawerStateForHealth(profileState),
        rows: [
          {
            label: "Active profile",
            value: profileData?.active_profile_label ?? "Not surfaced"
          },
          {
            label: "Core missing",
            value: String(profileData?.missing_core_dependency_ids?.length ?? 0)
          },
          {
            label: "Doctor",
            value: doctorData?.core_ready ? "Core ready" : humanize(doctorData?.overall_status)
          },
          { label: "Runtime mode", value: humanize(doctorData?.runtime_mode) },
          { label: "Workers enabled", value: String(enabledWorkers) },
          { label: "Autonomy", value: `Level ${String(effectiveControls.autonomy_level ?? "unknown")}` },
          { label: "GPU leases", value: String(cognitionData?.active_gpu_leases?.length ?? 0) },
          { label: "Emergency", value: cognitionData?.emergency?.active ? "STOP active" : "Ready" }
        ]
      }
    ];
  }, [
    data,
    healthState,
    healthySubsystemCount,
    loadState,
    enabledWorkers,
    profileData,
    profileState,
    doctorData,
    cognitionData,
    effectiveControls,
    subsystemCount
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);

    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  const overallDetail =
    loadState === "loading"
      ? "Health truth is being requested from the local bridge."
      : loadState === "error"
        ? "The Health room is mounted, but the local health endpoint did not return usable truth."
        : data?.healthy === true
          ? "The current health endpoint reports the local organism as healthy."
          : "The current health endpoint reports one or more incomplete, degraded, or unavailable conditions.";

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        minHeight: 0,
        height: "100%",
        overflowY: "auto",
        paddingRight: "0.1rem"
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
          Health
        </div>
        <h1
          style={{
            margin: 0,
            fontSize: "2.1rem",
            lineHeight: 1.1,
            color: palette.silver
          }}
        >
          Is the organism healthy right now?
        </h1>
        <div
          style={{
            marginTop: "0.65rem",
            color: palette.silverMuted,
            lineHeight: 1.6,
            maxWidth: "78ch"
          }}
        >
          This room reads the local <code>/status/health</code>, read-only{" "}
          <code>/status/profiles</code>, and non-repairing <code>/status/doctor</code>{" "}
          surfaces. It shows current body, XDG, authentication, dependency, and
          profile readiness without running a worker, model, installer, or repair.
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.85rem",
          alignItems: "center",
          padding: "0.85rem 1rem",
          borderRadius: "18px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.70) 0%, rgba(11, 14, 18, 0.76) 100%)"
        }}
      >
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.45
          }}
        >
          <strong style={{ color: palette.silver }}>Last check:</strong>{" "}
          {formatDateTime(data?.last_health_check_utc)}
          {" · "}
          <strong style={{ color: palette.silver }}>Startup ready:</strong>{" "}
          {startupReady ? "Yes" : "No"}
        </div>

        <button
          type="button"
          onClick={() => setRefreshIndex((value) => value + 1)}
          disabled={loadState === "loading"}
          style={{
            border: `1px solid ${palette.lineTeal}`,
            borderRadius: "12px",
            background:
              "linear-gradient(180deg, rgba(16, 41, 43, 0.60) 0%, rgba(18, 25, 37, 0.72) 100%)",
            color: palette.teal,
            cursor: loadState === "loading" ? "wait" : "pointer",
            fontWeight: 700,
            padding: "0.55rem 0.85rem"
          }}
        >
          {loadState === "loading" ? "Checking…" : "Refresh health"}
        </button>
      </div>

      <div
        className="elysia-summary-grid-4"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
          gap: "0.82rem"
        }}
      >
        <SummaryCard
          title="Overall"
          value={humanize(data?.health_state)}
          state={loadState === "error" ? "unavailable" : healthState}
          detail={overallDetail}
        />
        <SummaryCard
          title="Startup"
          value={humanize(data?.startup_state)}
          state={startupState}
          detail="Startup state is reported by the local health service, not guessed by the page."
        />
        <SummaryCard
          title="Local model"
          value={formatBoolean(data?.ollama_reachable)}
          state={data?.ollama_reachable === true ? "healthy" : "degraded"}
          detail="This reflects local Ollama reachability on loopback."
        />
        <SummaryCard
          title="SearXNG"
          value={formatBoolean(data?.searxng_reachable)}
          state={data?.searxng_reachable === true ? "healthy" : "degraded"}
          detail="This is a loopback-only reachability check and does not send search queries."
        />
        <SummaryCard
          title="Memory retrieval"
          value={humanize(String(cognitionHealth?.lexical_projection?.state ?? "unknown"))}
          state={cognitionHealth?.lexical_projection?.state === "ready" ? "healthy" : "degraded"}
          detail={`FTS ${String(cognitionHealth?.lexical_projection?.projection_version ?? "version unavailable")} · ${String(cognitionHealth?.lexical_projection?.indexed_normal_records ?? 0)} normal records · sealed index disabled.`}
        />
        <SummaryCard
          title="Research evidence"
          value={humanize(String(cognitionHealth?.research_evidence?.state ?? "unknown"))}
          state={cognitionHealth?.research_evidence?.state === "ready" ? "healthy" : "degraded"}
          detail={`${String(cognitionHealth?.research_evidence?.evidence_count ?? 0)} durable evidence records and ${String(cognitionHealth?.research_evidence?.research_session_count ?? 0)} sessions in account-scoped XDG storage.`}
        />
        <SummaryCard
          title="Semantic projection"
          value={humanize(String(cognitionHealth?.semantic_projection?.state ?? "unknown"))}
          state={
            ["ready", "optional_not_installed"].includes(String(cognitionHealth?.semantic_projection?.state ?? ""))
              ? "healthy"
              : "degraded"
          }
          detail={`Hybrid production decision: ${humanize(String(cognitionHealth?.semantic_projection?.promotion_decision ?? "unknown"))}. ${String(cognitionHealth?.semantic_projection?.indexed_normal_records ?? 0)} normal vectors · Private persistent vectors: no · Sealed vectors: no · FTS fallback remains live.`}
        />
        <SummaryCard
          title="Memory release lifecycle"
          value={humanize(String(cognitionHealth?.release_closure?.object_store?.state ?? "unknown"))}
          state={cognitionHealth?.release_closure?.object_store?.state === "ready" ? "healthy" : "degraded"}
          detail={`Canonical writers ${String(cognitionHealth?.release_closure?.canonical_writer_count ?? "unknown")} · graph ${humanize(String(cognitionHealth?.release_closure?.graph?.state ?? "unknown"))} · archive ${humanize(String(cognitionHealth?.release_closure?.archives?.state ?? "unknown"))} · scheduler jobs ${String(cognitionHealth?.release_closure?.scheduler?.length ?? 0)}.`}
        />
          <SummaryCard
            title="Writable records"
          value={`${writableReadyCount}/${writableBooleans.length} writable`}
          state={
            writableReadyCount === writableBooleans.length
              ? "healthy"
              : writableReadyCount > 0
                ? "degraded"
                : "unhealthy"
          }
          detail="Logging, journaling, and memory paths must be writable enough for normal governed use."
          />
        <SummaryCard
          title="Cognition Governor"
          value={`Level ${String(effectiveControls.autonomy_level ?? "unknown")}`}
          state={cognitionData?.governor_contract ? "healthy" : "degraded"}
          detail={`${String(cognitionData?.reasoning_gears?.length ?? 0)} reasoning gears · ${humanize(String(effectiveControls.preferred_reasoning_gear ?? "automatic"))} preference · content-free policy truth.`}
        />
        <SummaryCard
          title="Compute Governor"
          value={gpuDevices.length ? `${gpuDevices.length} GPU ready` : "CPU fallback"}
          state={computeTruth?.gpu?.available || computeTruth?.system ? "healthy" : "degraded"}
          detail={`${String(cognitionData?.active_gpu_leases?.length ?? 0)} active GPU leases · ${String(computeTruth?.active_job_count ?? 0)} active jobs · ${String(computeTruth?.oom_history?.length ?? 0)} bounded recent OOM incidents · ${modelRows.filter((row: any) => row.loaded).length} resident local models · no permanent embedding reservation.`}
        />
        <SummaryCard
          title="Emergency posture"
          value={cognitionData?.emergency?.active ? "STOP active" : "Ready"}
          state={cognitionData?.emergency?.active ? "degraded" : "healthy"}
          detail={cognitionData?.emergency?.active ? "New governed work is blocked until explicit Owner/Admin reset." : "System-wide cancellation authority is armed; durable preferences remain unchanged."}
        />
      </div>

      <div
        className="elysia-summary-grid-3"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: "0.82rem"
        }}
      >
        <ProgressBar
          label="Subsystem health"
          percent={subsystemReadinessPercent}
          detail={`${healthySubsystemCount}/${subsystemCount} subsystem entries currently report healthy.`}
        />
        <ProgressBar
          label="Core readiness"
          percent={coreReadinessPercent}
          detail={`${coreReadyCount}/${coreBooleans.length} core checks report ready: API, runtime, Ollama, and config.`}
        />
        <ProgressBar
          label="Writable local paths"
          percent={writableReadinessPercent}
          detail={`${writableReadyCount}/${writableBooleans.length} local write-path checks report ready.`}
        />
      </div>

      <section
        aria-label="Install profile readiness"
        style={{
          display: "grid",
          gap: "0.82rem",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineBronze}`,
          background:
            "linear-gradient(180deg, rgba(43, 31, 21, 0.22) 0%, rgba(11, 14, 18, 0.74) 100%)"
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "1rem",
            alignItems: "baseline"
          }}
        >
          <div>
            <div
              style={{
                fontSize: "0.82rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: palette.sandstone,
                marginBottom: "0.22rem"
              }}
            >
              Install profile readiness
            </div>
            <div style={{ color: palette.silverMuted, lineHeight: 1.5 }}>
              Safe module metadata and executable lookup only. This surface has
              no install, download, profile-enable, model-load, or worker-start authority.
            </div>
          </div>
          <StatusBadge state={profileState} />
        </div>

        <div
          className="elysia-summary-grid-4"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
            gap: "0.82rem"
          }}
        >
          <SummaryCard
            title="Active profile"
            value={profileData?.active_profile_label ?? "Not surfaced"}
            state={profileState}
            detail={`Readiness ${humanize(activeProfile?.readiness)}. Selection grants no operation approval.`}
          />
          <SummaryCard
            title="Dependency truth"
            value={`${presentDependencies} present`}
            state={missingDependencies > 0 ? "degraded" : profileState}
            detail={`${missingDependencies} required missing • ${optionalMissingDependencies} optional missing • ${gatedDependencies} profile/Lab gated.`}
          />
          <SummaryCard
            title="Local overrides"
            value={humanize(profileData?.local_overrides?.state)}
            state={
              profileData?.local_overrides?.state === "invalid_fail_closed"
                ? "degraded"
                : profileState
            }
            detail="Only configuration labels and counts are surfaced; raw values and paths remain withheld."
          />
          <SummaryCard
            title="Doctor / workers"
            value={profileData?.doctor_executed ? "Doctor executed" : "Doctor not executed"}
            state={enabledWorkers > 0 ? "degraded" : "unknown"}
            detail={`${enabledWorkers} workers enabled. Local doctor and isolation proof are still required.`}
          />
        </div>

        {profileWarnings.length > 0 ? (
          <HealthNoteList title="Profile cautions" notes={profileWarnings} tone="warm" />
        ) : null}
      </section>

      <ApplicationLifecyclePanel />

      <section
        aria-label="Core install doctor"
        style={{
          display: "grid",
          gap: "0.82rem",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineTeal}`,
          background:
            "linear-gradient(180deg, rgba(16, 41, 43, 0.24) 0%, rgba(11, 14, 18, 0.74) 100%)"
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "1rem",
            alignItems: "baseline"
          }}
        >
          <div>
            <div
              style={{
                fontSize: "0.82rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: palette.teal,
                marginBottom: "0.22rem"
              }}
            >
              Core install doctor
            </div>
            <div style={{ color: palette.silverMuted, lineHeight: 1.5 }}>
              Read-only readiness truth. Doctor does not install, repair, download,
              start a worker, or expose a credential or private path.
            </div>
          </div>
          <StatusBadge state={doctorState} />
        </div>

        <div
          className="elysia-summary-grid-4"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
            gap: "0.82rem"
          }}
        >
          <SummaryCard
            title="Core readiness"
            value={doctorData?.core_ready ? "Ready" : humanize(doctorData?.overall_status)}
            state={doctorState}
            detail="Required Core, API, path, authentication, and version checks only."
          />
          <SummaryCard
            title="Runtime mode"
            value={humanize(doctorData?.runtime_mode)}
            state={doctorData?.runtime_mode ? "ready" : "unknown"}
            detail="Source development and packaged lifecycle modes are distinguished explicitly."
          />
          <SummaryCard
            title="Local authentication"
            value={doctorData?.local_auth?.initialized ? "Initialized" : doctorData?.local_auth?.required_for_mutations ? "Required / missing" : "Development mode"}
            state={doctorData?.local_auth?.required_for_mutations && !doctorData?.local_auth?.initialized ? "degraded" : "ready"}
            detail="Packaged mutations require a private XDG runtime credential; its value is never rendered."
          />
          <SummaryCard
            title="User state"
            value={doctorData?.first_run?.state ? humanize(doctorData.first_run.state) : "Not surfaced"}
            state={doctorData?.first_run?.state === "ready" ? "ready" : "degraded"}
            detail="Config, data, cache, state, and runtime locations are user-local XDG roots, not source-tree defaults."
          />
        </div>
      </section>

      <section
        style={{
          display: "grid",
          gap: "0.82rem",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.74) 0%, rgba(11, 14, 18, 0.80) 100%)"
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "1rem",
            alignItems: "baseline"
          }}
        >
          <div>
            <div
              style={{
                fontSize: "0.82rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: palette.teal,
                marginBottom: "0.22rem"
              }}
            >
              Subsystems
            </div>
            <div
              style={{
                color: palette.silverMuted,
                lineHeight: 1.5
              }}
            >
              These cards show only subsystem truth returned by the health endpoint.
            </div>
          </div>

          <StatusBadge state={healthState} />
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "0.82rem"
          }}
        >
          {subsystemList.map((item) => (
            <SubsystemCard
              key={item.key}
              label={item.label}
              description={item.description}
              entry={item.entry}
            />
          ))}
        </div>
      </section>

      <div
        className="elysia-summary-grid-2"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: "0.85rem"
        }}
      >
        <HealthNoteList title="Warnings" notes={warningNotes} tone="warm" />
        <HealthNoteList title="Errors" notes={errorNotes} tone="cool" />
      </div>

      <section
        style={{
          padding: "1rem",
          borderRadius: "18px",
          border: `1px dashed ${palette.lineBronze}`,
          background: "rgba(11, 14, 18, 0.42)",
          color: palette.silverMuted,
          lineHeight: 1.58
        }}
      >
        <strong style={{ color: palette.sandstone }}>Not shown as live yet:</strong>{" "}
        live sandbox isolation, add-on bridge/code execution, worker execution,
        model loading, installer mutation, queue backlogs, and storage pressure. Presence truth is
        not activation truth, and this room does not invent either.
      </section>
    </div>
  );
}
