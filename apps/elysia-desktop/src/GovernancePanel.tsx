import type { ReactNode } from "react";

export type GovernancePanelTone = "neutral" | "warm" | "cool";

export type GovernancePanelProps = {
  title: string;
  description: string;
  children: ReactNode;
  note?: string | null;
  stateLabel?: string | null;
  sourceLabel?: string | null;
  compact?: boolean;
  tone?: GovernancePanelTone;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  lineTeal: "rgba(126, 215, 209, 0.24)"
} as const;

function getToneBorder(tone: GovernancePanelTone): string {
  switch (tone) {
    case "warm":
      return palette.lineBronze;
    case "cool":
      return palette.lineTeal;
    case "neutral":
    default:
      return palette.lineSilver;
  }
}

function getToneAccent(tone: GovernancePanelTone): string {
  switch (tone) {
    case "warm":
      return palette.bronze;
    case "cool":
      return palette.teal;
    case "neutral":
    default:
      return palette.sandstone;
  }
}

export default function GovernancePanel({
  title,
  description,
  children,
  note,
  stateLabel,
  sourceLabel,
  compact = false,
  tone = "neutral"
}: GovernancePanelProps) {
  const hasMeta = Boolean(stateLabel || sourceLabel);
  const borderColor = getToneBorder(tone);
  const accentColor = getToneAccent(tone);

  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        gap: compact ? "0.68rem" : "0.88rem",
        padding: compact ? "0.82rem 0.88rem" : "0.94rem 1rem",
        borderRadius: compact ? "16px" : "19px",
        border: `1px solid ${borderColor}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.52) 0%, rgba(11, 14, 18, 0.50) 100%)"
      }}
    >
      <div style={{ display: "grid", gap: "0.32rem" }}>
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "0.8rem"
          }}
        >
          <h2
            style={{
              margin: 0,
              fontSize: compact ? "0.95rem" : "1.01rem",
              lineHeight: 1.22,
              color: palette.silver,
              fontWeight: 700
            }}
          >
            {title}
          </h2>
        </div>

        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.5,
            maxWidth: "74ch",
            fontSize: compact ? "0.9rem" : "0.93rem"
          }}
        >
          {description}
        </div>

        {note ? (
          <div
            style={{
              color: accentColor,
              lineHeight: 1.4,
              fontSize: "0.8rem",
              maxWidth: "72ch"
            }}
          >
            {note}
          </div>
        ) : null}
      </div>

      {hasMeta ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.42rem"
          }}
        >
          {stateLabel ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "0.28rem 0.52rem",
                borderRadius: "999px",
                border: `1px solid ${borderColor}`,
                background: "rgba(18, 25, 37, 0.58)",
                color: palette.silver,
                fontSize: "0.72rem",
                lineHeight: 1.2
              }}
            >
              <strong style={{ color: accentColor, marginRight: "0.35rem" }}>
                State
              </strong>
              {stateLabel}
            </span>
          ) : null}

          {sourceLabel ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "0.32rem 0.56rem",
                borderRadius: "999px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(18, 25, 37, 0.58)",
                color: palette.silverMuted,
                fontSize: "0.74rem",
                lineHeight: 1.2
              }}
            >
              <strong style={{ color: palette.sandstone, marginRight: "0.35rem" }}>
                Source
              </strong>
              {sourceLabel}
            </span>
          ) : null}
        </div>
      ) : null}

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: compact ? "0.62rem" : "0.76rem",
          minWidth: 0
        }}
      >
        {children}
      </div>
    </section>
  );
}
