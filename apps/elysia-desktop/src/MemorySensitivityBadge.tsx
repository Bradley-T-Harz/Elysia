export type MemorySensitivityValue =
  | "public"
  | "internal"
  | "private"
  | "sealed";

type MemorySensitivityBadgeProps = {
  value: MemorySensitivityValue;
  compact?: boolean;
  title?: string;
  dimmed?: boolean;
};

const palette = {
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)"
} as const;

const MEMORY_SENSITIVITY_LABELS: Record<MemorySensitivityValue, string> = {
  public: "Public",
  internal: "Internal",
  private: "Private",
  sealed: "Sealed"
};

const MEMORY_SENSITIVITY_TONES: Record<
  MemorySensitivityValue,
  { border: string; background: string; color: string }
> = {
  public: {
    border: "rgba(47, 138, 104, 0.28)",
    background: "rgba(20, 42, 34, 0.30)",
    color: palette.emerald
  },
  internal: {
    border: "rgba(199, 210, 218, 0.16)",
    background: "rgba(24, 33, 48, 0.34)",
    color: palette.silver
  },
  private: {
    border: "rgba(138, 106, 60, 0.30)",
    background: "rgba(43, 31, 21, 0.34)",
    color: palette.sandstone
  },
  sealed: {
    border: "rgba(139, 78, 47, 0.34)",
    background: "rgba(43, 27, 20, 0.34)",
    color: "#D89A77"
  }
};

export default function MemorySensitivityBadge({
  value,
  compact = false,
  title,
  dimmed = false
}: MemorySensitivityBadgeProps) {
  const label = MEMORY_SENSITIVITY_LABELS[value];
  const tone = MEMORY_SENSITIVITY_TONES[value];

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
