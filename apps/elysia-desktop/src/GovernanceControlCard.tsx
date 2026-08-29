import type { ReactNode } from "react";
import type {
  GovernanceControl,
  GovernanceControlState,
  GovernanceMutationClassification
} from "./api/bridgeClient";

export type GovernanceControlCardProps = {
  control: GovernanceControl;
  compact?: boolean;
  showCategory?: boolean;
  showSourcePath?: boolean;
  showStateBadge?: boolean;
  displayValue?: ReactNode;
  actionSlot?: ReactNode;
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

const mutationMeta: Record<
  GovernanceMutationClassification,
  { label: string; color: string; border: string; background: string }
> = {
  "safe-live-editable-now": {
    label: "Live editable",
    color: palette.teal,
    border: "rgba(126, 215, 209, 0.28)",
    background: "rgba(16, 41, 43, 0.30)"
  },
  "plan-only": {
    label: "Plan-only",
    color: palette.bronze,
    border: "rgba(138, 106, 60, 0.28)",
    background: "rgba(43, 31, 21, 0.22)"
  },
  "read-only-constitutional": {
    label: "Read-only",
    color: palette.silver,
    border: "rgba(199, 210, 218, 0.18)",
    background: "rgba(24, 33, 48, 0.30)"
  },
  "profile-gated-later": {
    label: "Profile-gated",
    color: palette.sandstone,
    border: "rgba(184, 162, 123, 0.28)",
    background: "rgba(43, 31, 21, 0.24)"
  },
  "lab-gated-later": {
    label: "Lab-gated",
    color: palette.bronze,
    border: "rgba(138, 106, 60, 0.30)",
    background: "rgba(43, 31, 21, 0.24)"
  },
  "hard-prohibited-by-default": {
    label: "Hard-prohibited by default",
    color: palette.sandstone,
    border: "rgba(184, 162, 123, 0.34)",
    background: "rgba(58, 27, 25, 0.28)"
  }
};

function formatValue(value: string | boolean | number | null | undefined): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "number") {
    return String(value);
  }

  if (typeof value === "string" && value.trim()) {
    return value;
  }

  return "Not surfaced";
}

function formatCategory(value?: string | null): string | null {
  if (!value?.trim()) {
    return null;
  }

  return value.replace(/_/g, " ");
}

function formatSource(
  control: GovernanceControl,
  showSourcePath: boolean
): string {
  const label = control.source?.label?.trim();
  const path = control.source?.path?.trim();

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

export function GovernanceMutationBadge({
  classification
}: {
  classification: GovernanceMutationClassification;
}) {
  const meta = mutationMeta[classification];

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
        fontSize: "0.7rem",
        fontWeight: 700,
        letterSpacing: "0.035em",
        whiteSpace: "nowrap"
      }}
    >
      {meta.label}
    </span>
  );
}

export default function GovernanceControlCard({
  control,
  compact = false,
  showCategory = true,
  showSourcePath = true,
  showStateBadge = true,
  displayValue,
  actionSlot
}: GovernanceControlCardProps) {
  const categoryLabel = formatCategory(control.category);
  const sourceText = formatSource(control, showSourcePath);
  const resolvedValue = displayValue ?? formatValue(control.value);
  const hasFooter = Boolean(
    control.authority_note ||
      control.mutation_reason ||
      control.mutation_later_gate ||
      actionSlot
  );

  return (
    <div
      style={{
        display: "grid",
        gap: compact ? "0.48rem" : "0.58rem",
        padding: compact ? "0.82rem" : "0.92rem",
        borderRadius: compact ? "14px" : "16px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.78) 0%, rgba(11, 14, 18, 0.84) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "0.65rem"
        }}
      >
        <div style={{ display: "grid", gap: "0.24rem", minWidth: 0 }}>
          <strong
            style={{
              fontSize: compact ? "0.9rem" : "0.95rem",
              color: palette.silver,
              lineHeight: 1.35
            }}
          >
            {control.label}
          </strong>

          {showCategory && categoryLabel ? (
            <span
              style={{
                fontSize: "0.72rem",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: palette.silverMuted
              }}
            >
              {categoryLabel}
            </span>
          ) : null}
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "flex-end",
            gap: "0.34rem"
          }}
        >
          {showStateBadge ? <GovernanceStateBadge state={control.state} /> : null}
          {control.mutation_classification ? (
            <GovernanceMutationBadge classification={control.mutation_classification} />
          ) : null}
        </div>
      </div>

      <div
        style={{
          fontSize: compact ? "0.92rem" : "0.97rem",
          color: palette.teal,
          fontWeight: 600,
          lineHeight: 1.42,
          wordBreak: "break-word"
        }}
      >
        {resolvedValue}
      </div>

      {control.detail ? (
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.56,
            fontSize: compact ? "0.88rem" : "0.92rem"
          }}
        >
          {control.detail}
        </div>
      ) : null}

      <div
        style={{
          paddingTop: "0.44rem",
          borderTop: `1px solid rgba(199, 210, 218, 0.05)`,
          color: palette.silverMuted,
          fontSize: compact ? "0.74rem" : "0.76rem",
          lineHeight: 1.36
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
        {sourceText}
      </div>

      {hasFooter ? (
        <div
          style={{
            display: "grid",
            gap: "0.5rem"
          }}
        >
          {control.authority_note ? (
            <div
              style={{
                color: palette.silverMuted,
                lineHeight: 1.5,
                fontSize: "0.79rem"
              }}
            >
              {control.authority_note}
            </div>
          ) : null}

          {control.mutation_reason ? (
            <div
              style={{
                color: palette.silverMuted,
                lineHeight: 1.5,
                fontSize: "0.79rem"
              }}
            >
              <strong style={{ color: palette.sandstone, fontWeight: 600 }}>
                Mutation boundary:
              </strong>{" "}
              {control.mutation_reason}
            </div>
          ) : null}

          {control.mutation_later_gate ? (
            <div
              style={{
                color: palette.silverMuted,
                lineHeight: 1.5,
                fontSize: "0.77rem"
              }}
            >
              <strong style={{ color: palette.sandstone, fontWeight: 600 }}>
                Promotion gate:
              </strong>{" "}
              {control.mutation_later_gate}
            </div>
          ) : null}

          {actionSlot ? (
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end"
              }}
            >
              {actionSlot}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
