export type MemoryClassValue =
  | "working"
  | "conversation"
  | "project"
  | "research"
  | "operational"
  | "preference"
  | "sealed_private"
  | "audit";

type MemoryClassBadgeProps = {
  value: MemoryClassValue;
  compact?: boolean;
  title?: string;
  dimmed?: boolean;
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
  lineBronze: "rgba(138, 106, 60, 0.30)"
} as const;

const MEMORY_CLASS_LABELS: Record<MemoryClassValue, string> = {
  working: "Working",
  conversation: "Conversation",
  project: "Project",
  research: "Research",
  operational: "Operational",
  preference: "Preference",
  sealed_private: "Sealed private",
  audit: "Audit"
};

const MEMORY_CLASS_TONES: Record<
  MemoryClassValue,
  { border: string; background: string; color: string }
> = {
  working: {
    border: palette.lineSilver,
    background: "rgba(24, 33, 48, 0.34)",
    color: palette.silver
  },
  conversation: {
    border: "rgba(126, 215, 209, 0.24)",
    background: "rgba(16, 41, 43, 0.30)",
    color: palette.teal
  },
  project: {
    border: palette.lineBronze,
    background: "rgba(43, 31, 21, 0.34)",
    color: palette.sandstone
  },
  research: {
    border: "rgba(47, 138, 104, 0.28)",
    background: "rgba(20, 42, 34, 0.30)",
    color: palette.emerald
  },
  operational: {
    border: "rgba(184, 162, 123, 0.24)",
    background: "rgba(33, 32, 28, 0.30)",
    color: palette.silver
  },
  preference: {
    border: "rgba(126, 215, 209, 0.18)",
    background: "rgba(32, 35, 40, 0.34)",
    color: "#A8DDD9"
  },
  sealed_private: {
    border: "rgba(139, 78, 47, 0.34)",
    background: "rgba(43, 27, 20, 0.34)",
    color: "#D89A77"
  },
  audit: {
    border: "rgba(160, 170, 178, 0.24)",
    background: "rgba(29, 33, 39, 0.34)",
    color: palette.silverMuted
  }
};

export default function MemoryClassBadge({
  value,
  compact = false,
  title,
  dimmed = false
}: MemoryClassBadgeProps) {
  const label = MEMORY_CLASS_LABELS[value];
  const tone = MEMORY_CLASS_TONES[value];

  return (
    <span
      title={title ?? label}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        padding: compact ? "0.28rem 0.5rem" : "0.38rem 0.65rem",
        borderRadius: "999px",
        border: `1px solid ${tone.border}`,
        background: tone.background,
        color: tone.color,
        fontSize: compact ? "0.72rem" : "0.76rem",
        fontWeight: 700,
        letterSpacing: "0.04em",
        whiteSpace: "nowrap",
        opacity: dimmed ? 0.72 : 1
      }}
    >
      {label}
    </span>
  );
}
