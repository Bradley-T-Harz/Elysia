import type {
  GovernanceControl,
  GovernanceControlState,
  TrustZoneSummary
} from "./api/bridgeClient";
import { GovernanceMutationBadge } from "./GovernanceControlCard";

export type TrustZoneViewProps = {
  zones: TrustZoneSummary[];
  compact?: boolean;
  showSourcePath?: boolean;
  emptyMessage?: string;
  controls?: GovernanceControl[];
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)"
} as const;

const stateMeta: Record<
  GovernanceControlState,
  {
    label: string;
    color: string;
    border: string;
    background: string;
  }
> = {
  live_editable: {
    label: "Live editable",
    color: palette.teal,
    border: "rgba(126, 215, 209, 0.24)",
    background: "rgba(16, 41, 43, 0.26)"
  },
  display_only: {
    label: "Display-only",
    color: palette.silver,
    border: "rgba(199, 210, 218, 0.16)",
    background: "rgba(24, 33, 48, 0.28)"
  },
  inactive: {
    label: "Inactive",
    color: palette.sandstone,
    border: "rgba(138, 106, 60, 0.22)",
    background: "rgba(43, 31, 21, 0.24)"
  },
  planned: {
    label: "Planned",
    color: palette.bronze,
    border: "rgba(138, 106, 60, 0.28)",
    background: "rgba(43, 31, 21, 0.20)"
  }
};

function formatAccessState(value: string): string {
  return value.replace(/_/g, " ");
}

function formatBoolean(value: boolean | undefined): string {
  return value ? "Yes" : "No";
}

function formatSource(zone: TrustZoneSummary, showSourcePath: boolean): string {
  const label = zone.source?.label?.trim();
  const path = zone.source?.path?.trim();

  if (showSourcePath && label && path) {
    return `${label} · ${path}`;
  }

  if (label) {
    return label;
  }

  if (showSourcePath && path) {
    return path;
  }

  return "Source not surfaced";
}

function GovernanceStateBadge({ state }: { state: GovernanceControlState }) {
  const meta = stateMeta[state];

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "0.32rem 0.58rem",
        borderRadius: "999px",
        border: `1px solid ${meta.border}`,
        background: meta.background,
        color: meta.color,
        fontSize: "0.72rem",
        fontWeight: 700,
        letterSpacing: "0.04em",
        whiteSpace: "nowrap"
      }}
    >
      {meta.label}
    </span>
  );
}

function AccessPostureBadge({ value }: { value: TrustZoneSummary["access_state"] }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "0.28rem 0.52rem",
        borderRadius: "999px",
        border: `1px solid ${palette.lineBronze}`,
        background: "rgba(43, 31, 21, 0.20)",
        color: palette.sandstone,
        fontSize: "0.74rem",
        lineHeight: 1.2,
        textTransform: "capitalize"
      }}
    >
      {formatAccessState(value)}
    </span>
  );
}

function TrustZoneCard({
  zone,
  compact,
  showSourcePath,
  control
}: {
  zone: TrustZoneSummary;
  compact: boolean;
  showSourcePath: boolean;
  control?: GovernanceControl;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: compact ? "0.62rem" : "0.74rem",
        padding: compact ? "0.84rem" : "0.96rem",
        borderRadius: compact ? "14px" : "16px",
        border: `1px solid ${palette.lineBronze}`,
        background:
          "linear-gradient(180deg, rgba(43, 31, 21, 0.44) 0%, rgba(18, 25, 37, 0.72) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "0.7rem"
        }}
      >
        <div style={{ display: "grid", gap: "0.34rem", minWidth: 0 }}>
          <strong
            style={{
              fontSize: compact ? "0.9rem" : "0.96rem",
              color: palette.silver,
              lineHeight: 1.35
            }}
          >
            {zone.label}
          </strong>
          <AccessPostureBadge value={zone.access_state} />
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "flex-end",
            gap: "0.34rem"
          }}
        >
          <GovernanceStateBadge state={zone.state} />
          {control?.mutation_classification ? (
            <GovernanceMutationBadge
              classification={control.mutation_classification}
            />
          ) : null}
        </div>
      </div>

      {zone.description ? (
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.56,
            fontSize: compact ? "0.88rem" : "0.92rem"
          }}
        >
          {zone.description}
        </div>
      ) : null}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: "0.45rem 0.8rem"
        }}
      >
        {[
          ["Assistant read", formatBoolean(zone.assistant_can_read)],
          ["Assistant write", formatBoolean(zone.assistant_can_write)],
          ["User read", formatBoolean(zone.user_can_read)],
          ["User write", formatBoolean(zone.user_can_write)],
          ["Sealed", formatBoolean(zone.sealed)]
        ].map(([label, value]) => (
          <div
            key={label}
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "0.6rem",
              color: palette.silverMuted,
              fontSize: "0.84rem"
            }}
          >
            <span>{label}</span>
            <strong style={{ color: palette.silver }}>{value}</strong>
          </div>
        ))}
      </div>

      {zone.detail ? (
        <div
          style={{
            paddingTop: "0.55rem",
            borderTop: `1px solid rgba(199, 210, 218, 0.08)`,
            color: palette.silverMuted,
            lineHeight: 1.5,
            fontSize: compact ? "0.84rem" : "0.88rem"
          }}
        >
          {zone.detail}
        </div>
      ) : null}

      {control?.mutation_reason ? (
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.5,
            fontSize: compact ? "0.8rem" : "0.84rem"
          }}
        >
          <strong style={{ color: palette.sandstone, fontWeight: 600 }}>
            Mutation boundary:
          </strong>{" "}
          {control.mutation_reason}
        </div>
      ) : null}

      <div
        style={{
          paddingTop: "0.42rem",
          borderTop: `1px solid rgba(199, 210, 218, 0.05)`,
          color: palette.silverMuted,
          fontSize: compact ? "0.74rem" : "0.76rem",
          lineHeight: 1.38
        }}
      >
        <strong
          style={{
            color: palette.sandstone,
            fontWeight: 600
          }}
        >
          Source:
        </strong>{" "}
        {formatSource(zone, showSourcePath)}
      </div>
    </div>
  );
}

export default function TrustZoneView({
  zones,
  compact = false,
  showSourcePath = true,
  emptyMessage = "No trust zones were surfaced by the current governance payload.",
  controls = []
}: TrustZoneViewProps) {
  if (!zones.length) {
    return (
      <div
        style={{
          padding: compact ? "0.9rem" : "1rem",
          borderRadius: compact ? "14px" : "16px",
          border: `1px dashed ${palette.lineBronze}`,
          background: "rgba(11, 14, 18, 0.42)",
          color: palette.silverMuted,
          lineHeight: 1.6
        }}
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
        gap: compact ? "0.68rem" : "0.82rem"
      }}
    >
      {zones.map((zone) => (
        <TrustZoneCard
          key={zone.zone_id}
          zone={zone}
          compact={compact}
          showSourcePath={showSourcePath}
          control={controls.find(
            (control) => control.control_id === `trust_zone_${zone.zone_id}`
          )}
        />
      ))}
    </div>
  );
}
