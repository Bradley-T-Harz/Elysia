import { useEffect, useMemo, useState } from "react";
import {
  fetchInstallProfileStatus,
  type InstallProfileStatusEnvelope
} from "./api/bridgeClient";
import {
  useCapabilityManifest,
  type CapabilityManifestEntry
} from "./hooks/useCapabilityManifest";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";

type CapabilitiesPageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
};

type BadgeTone =
  | "live"
  | "partial"
  | "planned"
  | "inactive"
  | "unavailable"
  | "degraded"
  | "blocked"
  | "unknown";

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
  lineTeal: "rgba(126, 215, 209, 0.24)"
} as const;

const commonStateFilters = [
  "all",
  "live",
  "partial",
  "planned",
  "inactive",
  "unavailable",
  "degraded",
  "blocked"
] as const;

function normalizeForCompare(value: string): string {
  return value.trim().toLowerCase();
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

function stateTone(value?: string | null): BadgeTone {
  const normalized = normalizeForCompare(value ?? "");

  if (
    normalized === "live" ||
    normalized === "partial" ||
    normalized === "planned" ||
    normalized === "inactive" ||
    normalized === "unavailable" ||
    normalized === "degraded" ||
    normalized === "blocked"
  ) {
    return normalized;
  }

  return "unknown";
}

function drawerStateFromCatalog(value?: string | null): DrawerSection["state"] {
  const tone = stateTone(value);

  switch (tone) {
    case "live":
      return "live";
    case "degraded":
    case "blocked":
      return "degraded";
    case "unavailable":
      return "unavailable";
    case "inactive":
      return "inactive";
    case "planned":
      return "planned";
    case "partial":
    case "unknown":
    default:
      return "partial";
  }
}

function badgeColors(tone: BadgeTone) {
  switch (tone) {
    case "live":
      return {
        label: "Live",
        color: palette.teal,
        border: "rgba(126, 215, 209, 0.32)",
        background: "rgba(126, 215, 209, 0.08)"
      };
    case "partial":
      return {
        label: "Partial",
        color: palette.sandstone,
        border: "rgba(184, 162, 123, 0.34)",
        background: "rgba(184, 162, 123, 0.10)"
      };
    case "planned":
      return {
        label: "Planned",
        color: palette.bronze,
        border: "rgba(138, 106, 60, 0.36)",
        background: "rgba(138, 106, 60, 0.10)"
      };
    case "inactive":
      return {
        label: "Inactive",
        color: palette.silverMuted,
        border: "rgba(199, 210, 218, 0.18)",
        background: "rgba(199, 210, 218, 0.05)"
      };
    case "unavailable":
      return {
        label: "Unavailable",
        color: "#D8A5A5",
        border: "rgba(216, 165, 165, 0.34)",
        background: "rgba(216, 165, 165, 0.08)"
      };
    case "degraded":
      return {
        label: "Degraded",
        color: "#D7A97E",
        border: "rgba(215, 169, 126, 0.34)",
        background: "rgba(215, 169, 126, 0.09)"
      };
    case "blocked":
      return {
        label: "Blocked",
        color: "#E0A0A0",
        border: "rgba(224, 160, 160, 0.38)",
        background: "rgba(224, 160, 160, 0.09)"
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

function PillBadge({
  value,
  fallback,
  tone
}: {
  value?: string | null;
  fallback?: string;
  tone?: BadgeTone;
}) {
  const resolvedTone = tone ?? stateTone(value);
  const colors = badgeColors(resolvedTone);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "max-content",
        padding: "0.22rem 0.56rem",
        borderRadius: "999px",
        border: `1px solid ${colors.border}`,
        background: colors.background,
        color: colors.color,
        fontSize: "0.68rem",
        fontWeight: 700,
        letterSpacing: "0.055em",
        textTransform: "uppercase",
        whiteSpace: "nowrap"
      }}
    >
      {value?.trim() ? humanize(value) : fallback ?? colors.label}
    </span>
  );
}

function ReadOnlyBadge({ readOnly }: { readOnly: boolean }) {
  return (
    <PillBadge
      value={readOnly ? "read only" : "action contract"}
      tone={readOnly ? "inactive" : "planned"}
    />
  );
}

function SummaryCard({
  title,
  value,
  detail,
  tone = "partial"
}: {
  title: string;
  value: string;
  detail: string;
  tone?: BadgeTone;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: "0.48rem",
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
        <PillBadge value={tone} tone={tone} />
      </div>

      <div
        style={{
          color: palette.silver,
          fontWeight: 750,
          fontSize: "1.06rem",
          lineHeight: 1.32
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

function FieldRow({
  label,
  value
}: {
  label: string;
  value: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "130px minmax(0, 1fr)",
        gap: "0.75rem",
        alignItems: "baseline",
        padding: "0.5rem 0",
        borderBottom: `1px solid rgba(199, 210, 218, 0.08)`
      }}
    >
      <div
        style={{
          color: palette.sandstone,
          fontSize: "0.76rem",
          letterSpacing: "0.07em",
          textTransform: "uppercase"
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: value === "Not surfaced" ? palette.silverMuted : palette.silver,
          lineHeight: 1.45,
          minWidth: 0,
          overflowWrap: "anywhere"
        }}
      >
        {value}
      </div>
    </div>
  );
}

function CapabilityCard({
  capability,
  selected,
  onSelect
}: {
  capability: CapabilityManifestEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{
        width: "100%",
        display: "grid",
        gap: "0.66rem",
        textAlign: "left",
        padding: "0.94rem",
        borderRadius: "18px",
        border: selected
          ? `1px solid ${palette.lineTeal}`
          : `1px solid ${palette.lineSilver}`,
        background: selected
          ? "linear-gradient(180deg, rgba(16, 41, 43, 0.58) 0%, rgba(18, 25, 37, 0.78) 100%)"
          : "linear-gradient(180deg, rgba(18, 25, 37, 0.70) 0%, rgba(11, 14, 18, 0.74) 100%)",
        color: palette.silver,
        cursor: "pointer",
        boxShadow: selected ? "0 0 24px rgba(126, 215, 209, 0.12)" : "none"
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
        <div style={{ display: "grid", gap: "0.18rem", minWidth: 0 }}>
          <strong
            style={{
              fontSize: "1rem",
              color: selected ? palette.teal : palette.silver
            }}
          >
            {capability.displayName}
          </strong>
          <span
            style={{
              color: palette.silverMuted,
              fontSize: "0.78rem",
              overflowWrap: "anywhere"
            }}
          >
            {capability.capabilityKey}
          </span>
        </div>

        <PillBadge value={capability.state} />
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.48,
          fontSize: "0.88rem"
        }}
      >
        {capability.summary || "No summary was returned by the manifest."}
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.4rem"
        }}
      >
        <PillBadge value={capability.group} tone="partial" />
        <PillBadge value={capability.locality} tone="inactive" />
        <PillBadge value={capability.approvalState} tone="planned" />
        <ReadOnlyBadge readOnly={capability.readOnly} />
      </div>
    </button>
  );
}

function DetailPanel({
  capability
}: {
  capability?: CapabilityManifestEntry | null;
}) {
  if (!capability) {
    return (
      <section
        style={{
          display: "grid",
          alignContent: "center",
          minHeight: "320px",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.78) 100%)",
          color: palette.silverMuted,
          lineHeight: 1.55
        }}
      >
        Select a capability to inspect its endpoint, surfaces, notes, locality,
        approval posture, and read-only truth.
      </section>
    );
  }

  return (
    <section
      style={{
        display: "grid",
        gap: "0.9rem",
        alignContent: "start",
        padding: "1rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.74) 0%, rgba(11, 14, 18, 0.82) 100%)",
        minHeight: 0
      }}
    >
      <div
        style={{
          display: "grid",
          gap: "0.36rem"
        }}
      >
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.11em",
            textTransform: "uppercase",
            color: palette.sandstone
          }}
        >
          Capability details
        </div>
        <h2
          style={{
            margin: 0,
            color: palette.silver,
            fontSize: "1.28rem",
            lineHeight: 1.2
          }}
        >
          {capability.displayName}
        </h2>
        <div
          style={{
            color: palette.silverMuted,
            overflowWrap: "anywhere"
          }}
        >
          {capability.capabilityKey}
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
        <PillBadge value={capability.state} />
        <PillBadge value={capability.group} tone="partial" />
        <PillBadge value={capability.locality} tone="inactive" />
        <PillBadge value={capability.approvalState} tone="planned" />
        <ReadOnlyBadge readOnly={capability.readOnly} />
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.58
        }}
      >
        {capability.summary || "No summary was returned by the manifest."}
      </div>

      <div style={{ display: "grid" }}>
        <FieldRow
          label="Endpoint"
          value={capability.supportingEndpoint || "Not surfaced"}
        />
        <FieldRow
          label="UI surfaces"
          value={
            capability.uiSurfaces.length > 0
              ? capability.uiSurfaces.join(", ")
              : "Not surfaced"
          }
        />
        <FieldRow
          label="Locality"
          value={capability.locality || "Not surfaced"}
        />
        <FieldRow
          label="Approval"
          value={capability.approvalState || "Not surfaced"}
        />
        <FieldRow
          label="Read only"
          value={capability.readOnly ? "Yes" : "No"}
        />
      </div>

      <section
        style={{
          display: "grid",
          gap: "0.55rem",
          padding: "0.85rem",
          borderRadius: "16px",
          border: `1px solid ${palette.lineBronze}`,
          background:
            "linear-gradient(180deg, rgba(43, 31, 21, 0.32) 0%, rgba(18, 25, 37, 0.70) 100%)"
        }}
      >
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.bronze
          }}
        >
          Manifest notes
        </div>

        {capability.notes.length > 0 ? (
          <ul
            style={{
              margin: 0,
              paddingLeft: "1.15rem",
              color: palette.silverMuted,
              lineHeight: 1.55
            }}
          >
            {capability.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : (
          <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
            No notes were returned by the manifest for this capability.
          </div>
        )}
      </section>
    </section>
  );
}

export default function CapabilitiesPage({
  startupReady,
  onRightDrawerSectionsChange
}: CapabilitiesPageProps) {
  const {
    capabilityStartupState,
    capabilityStatusMessage,
    capabilityStatusDetail,
    capabilityContractVersion,
    capabilityCatalogState,
    capabilityCount,
    capabilityGroups,
    capabilityWarnings,
    capabilities
  } = useCapabilityManifest();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("all");
  const [selectedState, setSelectedState] = useState("all");
  const [selectedCapabilityKey, setSelectedCapabilityKey] = useState("");
  const [profileEnvelope, setProfileEnvelope] =
    useState<InstallProfileStatusEnvelope | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function readProfileTruth() {
      try {
        const result = await fetchInstallProfileStatus();
        if (!cancelled) {
          setProfileEnvelope(result.payload);
        }
      } catch {
        if (!cancelled) {
          setProfileEnvelope(null);
        }
      }
    }

    void readProfileTruth();
    return () => {
      cancelled = true;
    };
  }, []);

  const profileData = profileEnvelope?.data;
  const profileTierRows = [
    {
      key: "core_v1_default",
      label: "Core v1 default",
      tone: "live" as BadgeTone
    },
    {
      key: "optional_v1_profile",
      label: "Optional v1 profile",
      tone: "partial" as BadgeTone
    },
    {
      key: "v1_lab_or_developer_gated",
      label: "v1 Lab / Developer-gated",
      tone: "planned" as BadgeTone
    },
    {
      key: "hard_prohibited_by_default",
      label: "Hard-prohibited by default",
      tone: "blocked" as BadgeTone
    }
  ].map((tier) => ({
    ...tier,
    items: profileData?.capability_tiers?.[tier.key] ?? []
  }));

  const manifestGroups = useMemo(() => {
    const fromManifest = capabilityGroups.filter((group) => group.trim());
    const fromCapabilities = Array.from(
      new Set(capabilities.map((capability) => capability.group).filter(Boolean))
    );

    return Array.from(new Set([...fromManifest, ...fromCapabilities])).sort(
      (a, b) => a.localeCompare(b)
    );
  }, [capabilities, capabilityGroups]);

  const manifestStates = useMemo(() => {
    const states = Array.from(
      new Set(
        capabilities
          .map((capability) => normalizeForCompare(capability.state))
          .filter(Boolean)
      )
    );

    return Array.from(
      new Set([
        ...commonStateFilters,
        ...states
      ])
    );
  }, [capabilities]);

  const filteredCapabilities = useMemo(() => {
    const query = normalizeForCompare(searchQuery);

    return capabilities.filter((capability) => {
      const matchesQuery =
        !query ||
        normalizeForCompare(capability.displayName).includes(query) ||
        normalizeForCompare(capability.capabilityKey).includes(query) ||
        normalizeForCompare(capability.summary).includes(query) ||
        normalizeForCompare(capability.group).includes(query) ||
        capability.notes.some((note) => normalizeForCompare(note).includes(query));

      const matchesGroup =
        selectedGroup === "all" || capability.group === selectedGroup;

      const matchesState =
        selectedState === "all" ||
        normalizeForCompare(capability.state) === selectedState;

      return matchesQuery && matchesGroup && matchesState;
    });
  }, [capabilities, searchQuery, selectedGroup, selectedState]);

  const selectedCapability = useMemo(() => {
    return (
      filteredCapabilities.find(
        (capability) => capability.capabilityKey === selectedCapabilityKey
      ) ??
      filteredCapabilities[0] ??
      null
    );
  }, [filteredCapabilities, selectedCapabilityKey]);

  const stateCounts = useMemo(() => {
    return capabilities.reduce<Record<string, number>>((counts, capability) => {
      const key = normalizeForCompare(capability.state) || "unknown";
      counts[key] = (counts[key] ?? 0) + 1;
      return counts;
    }, {});
  }, [capabilities]);

  const liveCount = stateCounts.live ?? 0;
  const unavailableCount = stateCounts.unavailable ?? 0;
  const degradedCount = stateCounts.degraded ?? 0;
  const plannedCount = stateCounts.planned ?? 0;
  const warningCount = capabilityWarnings.length;

  const catalogDrawerState = drawerStateFromCatalog(capabilityCatalogState);

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    return [
      {
        key: "active_context",
        title: "Active Context",
        state: catalogDrawerState,
        accent: "warm",
        rows: [
          { label: "Room", value: "Capabilities" },
          { label: "Surface", value: "Read-only limb map" },
          {
            label: "Source",
            value: "/status/capabilities through useCapabilityManifest"
          }
        ]
      },
      {
        key: "capability_catalog",
        title: "Capability Catalog",
        state: catalogDrawerState,
        rows: [
          { label: "Catalog state", value: humanize(capabilityCatalogState) },
          { label: "Capability count", value: String(capabilityCount) },
          { label: "Groups", value: String(manifestGroups.length) },
          {
            label: "Contract",
            value: capabilityContractVersion || "Not surfaced"
          }
        ]
      },
      {
        key: "operator_boundary",
        title: "Boundary / Control Posture",
        state: "inactive",
        rows: [
          { label: "Inspection", value: "Read-only" },
          { label: "Install/delete/toggle", value: "No route exposed here" },
          { label: "Operator controls", value: "Deferred to a protected manager" }
        ]
      },
      {
        key: "install_profile_truth",
        title: "Install Profile Truth",
        state:
          profileEnvelope?.status === "degraded"
            ? "degraded"
            : profileEnvelope?.status === "ok"
              ? "live"
              : "inactive",
        rows: [
          {
            label: "Active",
            value: profileData?.active_profile_label ?? "Not surfaced"
          },
          {
            label: "Resolution",
            value: humanize(profileData?.resolution_state)
          },
          {
            label: "Install authority",
            value: profileData?.install_authority_available ? "Available" : "None"
          }
        ]
      },
      {
        key: "capability_warnings",
        title: "Warnings",
        state: warningCount > 0 ? "degraded" : "inactive",
        rows: [
          { label: "Warning count", value: String(warningCount) },
          {
            label: "First warning",
            value: capabilityWarnings[0] ?? "No warnings returned"
          }
        ]
      }
    ];
  }, [
    capabilityCatalogState,
    capabilityContractVersion,
    capabilityCount,
    capabilityWarnings,
    catalogDrawerState,
    manifestGroups.length,
    profileData,
    profileEnvelope?.status,
    warningCount
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);

    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  const isChecking = capabilityStartupState === "checking";
  const isUnavailable =
    capabilityStartupState === "unavailable" ||
    capabilityStartupState === "error";

  function clearFilters() {
    setSearchQuery("");
    setSelectedGroup("all");
    setSelectedState("all");
    setSelectedCapabilityKey("");
  }

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        minHeight: 0,
        height: "100%",
        overflow: "hidden"
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
          Capabilities
        </div>
        <h1
          style={{
            margin: 0,
            fontSize: "2.1rem",
            lineHeight: 1.1,
            color: palette.silver
          }}
        >
          Truth map of Elysia’s limbs.
        </h1>
        <div
          style={{
            marginTop: "0.65rem",
            color: palette.silverMuted,
            lineHeight: 1.6,
            maxWidth: "84ch"
          }}
        >
          This room is read-only and driven by <code>/status/capabilities</code>.
          It shows declared capability truth, not package-management controls.
          Existing action contracts remain in their owning governed rooms; this
          catalog never makes a capability available by itself.
        </div>
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
          title="Catalog state"
          value={humanize(capabilityCatalogState || capabilityStartupState)}
          detail={capabilityStatusMessage}
          tone={stateTone(capabilityCatalogState)}
        />
        <SummaryCard
          title="Capability count"
          value={String(capabilityCount)}
          detail={`${filteredCapabilities.length} visible after current filters.`}
          tone="live"
        />
        <SummaryCard
          title="Groups"
          value={String(manifestGroups.length)}
          detail={
            manifestGroups.length > 0
              ? manifestGroups.join(", ")
              : "No groups were returned by the manifest."
          }
          tone="partial"
        />
        <SummaryCard
          title="Warnings"
          value={String(warningCount)}
          detail={
            warningCount > 0
              ? capabilityWarnings[0]
              : "No manifest warnings were returned."
          }
          tone={warningCount > 0 ? "degraded" : "inactive"}
        />
      </div>

      <details
        style={{
          padding: "0.9rem",
          borderRadius: "18px",
          border: `1px solid ${palette.lineBronze}`,
          background: "rgba(11, 14, 18, 0.56)"
        }}
      >
        <summary
          style={{
            cursor: "pointer",
            color: palette.sandstone,
            fontWeight: 700
          }}
        >
          Install profile capability tiers · {profileData?.active_profile_label ?? "profile truth unavailable"}
        </summary>
        <div
          className="elysia-summary-grid-4"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
            gap: "0.7rem",
            marginTop: "0.78rem"
          }}
        >
          {profileTierRows.map((tier) => (
            <section
              key={tier.key}
              style={{
                display: "grid",
                alignContent: "start",
                gap: "0.5rem",
                padding: "0.72rem",
                borderRadius: "14px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(18, 25, 37, 0.62)"
              }}
            >
              <PillBadge value={tier.label} tone={tier.tone} />
              <div style={{ color: palette.silverMuted, fontSize: "0.78rem" }}>
                {tier.items.length} declared capabilities
              </div>
              {tier.items.length > 0 ? (
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: "1rem",
                    color: palette.silverMuted,
                    fontSize: "0.76rem",
                    lineHeight: 1.45
                  }}
                >
                  {tier.items.map((item) => (
                    <li key={item}>{humanize(item)}</li>
                  ))}
                </ul>
              ) : (
                <div style={{ color: palette.silverMuted, fontSize: "0.76rem" }}>
                  Tier truth unavailable.
                </div>
              )}
            </section>
          ))}
        </div>
        <div
          style={{
            marginTop: "0.7rem",
            color: palette.silverMuted,
            fontSize: "0.78rem",
            lineHeight: 1.5
          }}
        >
          Profile selection installs nothing, starts no worker, grants no
          approval, and cannot promote a prohibited capability.
        </div>
      </details>

      <section
        style={{
          display: "grid",
          gap: "0.75rem",
          padding: "0.9rem",
          borderRadius: "18px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.76) 100%)"
        }}
      >
        <div
          className="elysia-toolbar-grid-4"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(240px, 1fr) 180px 180px auto",
            gap: "0.7rem",
            alignItems: "center"
          }}
        >
          <input
            aria-label="Search capabilities"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search capabilities..."
            style={{
              minWidth: 0,
              padding: "0.66rem 0.78rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.72)",
              color: palette.silver,
              outline: "none"
            }}
          />

          <select
            aria-label="Filter capability group"
            value={selectedGroup}
            onChange={(event) => setSelectedGroup(event.target.value)}
            style={{
              minWidth: 0,
              padding: "0.66rem 0.78rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.72)",
              color: palette.silver,
              outline: "none"
            }}
          >
            <option value="all">All groups</option>
            {manifestGroups.map((group) => (
              <option key={group} value={group}>
                {humanize(group)}
              </option>
            ))}
          </select>

          <select
            aria-label="Filter capability state"
            value={selectedState}
            onChange={(event) => setSelectedState(event.target.value)}
            style={{
              minWidth: 0,
              padding: "0.66rem 0.78rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.72)",
              color: palette.silver,
              outline: "none"
            }}
          >
            {manifestStates.map((state) => (
              <option key={state} value={state}>
                {state === "all" ? "All states" : humanize(state)}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={clearFilters}
            style={{
              padding: "0.66rem 0.85rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineBronze}`,
              background:
                "linear-gradient(180deg, rgba(43, 31, 21, 0.44) 0%, rgba(18, 25, 37, 0.72) 100%)",
              color: palette.sandstone,
              cursor: "pointer",
              fontWeight: 700,
              whiteSpace: "nowrap"
            }}
          >
            Clear filters
          </button>
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.45rem",
            color: palette.silverMuted,
            lineHeight: 1.5
          }}
        >
          <PillBadge value={`live ${liveCount}`} tone="live" />
          <PillBadge value={`unavailable ${unavailableCount}`} tone="unavailable" />
          <PillBadge value={`degraded ${degradedCount}`} tone="degraded" />
          <PillBadge value={`planned ${plannedCount}`} tone="planned" />
          <span>
            {capabilityStatusDetail || "Capability manifest detail not surfaced."}
          </span>
        </div>
      </section>

      {isChecking ? (
        <EmptyState
          title="Capability manifest is being requested from the local bridge."
          detail="Waiting for /status/capabilities through useCapabilityManifest."
        />
      ) : isUnavailable ? (
        <EmptyState
          title="Capability manifest unavailable."
          detail={capabilityStatusDetail}
        />
      ) : capabilities.length === 0 ? (
        <EmptyState
          title="No capabilities were returned by the manifest."
          detail="This room does not create fake sample capabilities."
        />
      ) : (
        <div
          className="elysia-responsive-split"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(320px, 0.95fr) minmax(360px, 1.05fr)",
            gap: "1rem",
            minHeight: 0,
            flex: 1
          }}
        >
          <section
            className="elysia-stacked-pane"
            style={{
              display: "grid",
              gap: "0.7rem",
              alignContent: "start",
              minHeight: 0,
              overflowY: "auto",
              paddingRight: "0.1rem"
            }}
          >
            {filteredCapabilities.length > 0 ? (
              filteredCapabilities.map((capability) => (
                <CapabilityCard
                  key={capability.capabilityKey}
                  capability={capability}
                  selected={
                    selectedCapability?.capabilityKey === capability.capabilityKey
                  }
                  onSelect={() =>
                    setSelectedCapabilityKey(capability.capabilityKey)
                  }
                />
              ))
            ) : (
              <EmptyState
                title="No capabilities match the current filters."
                detail="Clear filters to return to the full manifest."
                compact
              />
            )}
          </section>

          <DetailPanel capability={selectedCapability} />
        </div>
      )}

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
        <strong style={{ color: palette.sandstone }}>Operator boundary:</strong>{" "}
        this page intentionally does not include install, staging, registry-state,
        package scanning, model mutation, Tauri permission editing, outbound, or
        autonomous repair controls. Inspecting a catalog entry grants no authority.
      </section>
    </div>
  );
}

function EmptyState({
  title,
  detail,
  compact = false
}: {
  title: string;
  detail: string;
  compact?: boolean;
}) {
  return (
    <section
      style={{
        display: "grid",
        alignContent: "center",
        minHeight: compact ? "160px" : "280px",
        padding: "1rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.78) 100%)"
      }}
    >
      <div
        style={{
          display: "grid",
          gap: "0.45rem",
          maxWidth: "68ch"
        }}
      >
        <strong style={{ color: palette.silver, fontSize: "1.05rem" }}>
          {title}
        </strong>
        <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
          {detail}
        </div>
      </div>
    </section>
  );
}
