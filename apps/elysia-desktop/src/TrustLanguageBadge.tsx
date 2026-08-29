import type { CSSProperties } from "react";
import {
  palette,
  trustToneTokens,
  type TrustBadge,
  type TrustTone
} from "./themeTokens";

type TrustLanguageBadgeProps = {
  badge: TrustBadge;
  density?: "regular" | "compact";
};

function getBadgeStyle(
  tone: TrustTone,
  density: "regular" | "compact"
): CSSProperties {
  const common: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.45rem",
    padding: density === "compact" ? "0.4rem 0.68rem" : "0.45rem 0.7rem",
    borderRadius: "999px",
    border: `1px solid ${palette.lineSilver}`,
    fontSize: "0.78rem",
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    whiteSpace: "nowrap",
    backdropFilter: "blur(8px)"
  };

  const toneTokens = trustToneTokens[tone];

  return {
    ...common,
    color: toneTokens.text,
    borderColor: toneTokens.border,
    background: toneTokens.background,
    boxShadow: toneTokens.glow
  };
}

function SignalDot({
  tone,
  density
}: {
  tone: TrustTone;
  density: "regular" | "compact";
}) {
  const size = density === "compact" ? "0.5rem" : "0.52rem";

  return (
    <span
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        borderRadius: "999px",
        background: trustToneTokens[tone].dot,
        boxShadow: `0 0 12px ${trustToneTokens[tone].dot}`
      }}
    />
  );
}

export default function TrustLanguageBadge({
  badge,
  density = "regular"
}: TrustLanguageBadgeProps) {
  return (
    <div style={getBadgeStyle(badge.tone, density)}>
      <SignalDot tone={badge.tone} density={density} />
      <span>{badge.label}</span>
    </div>
  );
}
