export type MemoryMutabilityValue =
  | "live_editable"
  | "append_only"
  | "review_required"
  | "immutable"
  | "not_yet_live";

type MemoryMutabilityBadgeProps = {
  value: MemoryMutabilityValue;
  compact?: boolean;
  title?: string;
  dimmed?: boolean;
};

const palette = {
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)"
} as const;

const MEMORY_MUTABILITY_LABELS: Record<MemoryMutabilityValue, string> = {
  live_editable: "Live editable",
  append_only: "Append only",
  review_required: "Review required",
  immutable: "Immutable",
  not_yet_live: "Not yet live"
};

const MEMORY_MUTABILITY_TONES: Record<
  MemoryMutabilityValue,
  { border: string; background: string; color: string }
> = {
  live_editable: {
    border: "rgba(126, 215, 209, 0.24)",
    background: "rgba(16, 41, 43, 0.30)",
    color: palette.teal
  },
  append_only: {
    border: "rgba(199, 210, 218, 0.16)",
    background: "rgba(24, 33, 48, 0.34)",
    color: palette.silver
  },
  review_required: {
    border: "rgba(138, 106, 60, 0.30)",
    background: "rgba(43, 31, 21, 0.34)",
    color: palette.sandstone
  },
  immutable: {
    border: "rgba(139, 78, 47, 0.34)",
    background: "rgba(43, 27, 20, 0.34)",
    color: "#D89A77"
  },
  not_yet_live: {
    border: "rgba(138, 106, 60, 0.22)",
    background: "rgba(33, 32, 28, 0.30)",
    color: palette.silverMuted
  }
};

export default function MemoryMutabilityBadge({
  value,
  compact = false,
  title,
  dimmed = false
}: MemoryMutabilityBadgeProps) {
  const label = MEMORY_MUTABILITY_LABELS[value];
  const tone = MEMORY_MUTABILITY_TONES[value];

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
