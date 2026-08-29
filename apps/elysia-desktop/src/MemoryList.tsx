import MemoryItemCard, {
  type MemoryItemCardActionAvailability,
  type MemoryItemCardData
} from "./MemoryItemCard";

type MemoryListProps = {
  items: MemoryItemCardData[];
  isLoading?: boolean;
  error?: string | null;
  hasActiveFilters?: boolean;
  emptyTitle?: string;
  emptyDetail?: string;
  showRoomTruthNote?: boolean;
  actions?: MemoryItemCardActionAvailability;
  onPin?: (memoryId: string) => void;
  onMove?: (memoryId: string) => void;
  onEdit?: (memoryId: string) => void;
  onForget?: (memoryId: string) => void;
  onArchive?: (memoryId: string) => void;
  onHistory?: (memoryId: string) => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)"
} as const;

export default function MemoryList({
  items,
  isLoading = false,
  error = null,
  hasActiveFilters = false,
  emptyTitle,
  emptyDetail,
  showRoomTruthNote = false,
  actions,
  onPin,
  onMove,
  onEdit,
  onForget,
  onArchive,
  onHistory
}: MemoryListProps) {
  if (error) {
    return (
      <ListStatePanel
        eyebrow="Memory list"
        title="Memory items could not be loaded."
        detail={error}
        tone="bronze"
      />
    );
  }

  if (isLoading) {
    return (
      <section
        style={{
          display: "grid",
          gap: "0.85rem",
          minHeight: 0,
          flex: 1
        }}
      >
        <ListStatePanel
          eyebrow="Memory list"
          title="Loading visible memory slice..."
          detail="The room is mounted and waiting on live item truth."
          tone="teal"
        />

        {[1, 2, 3].map((placeholder) => (
          <div
            key={placeholder}
            style={{
              minHeight: "142px",
              borderRadius: "18px",
              border: `1px dashed ${
                placeholder === 2 ? palette.lineBronze : palette.lineSilver
              }`,
              background:
                placeholder === 2
                  ? "rgba(43, 31, 21, 0.18)"
                  : "rgba(11, 14, 18, 0.42)"
            }}
          />
        ))}
      </section>
    );
  }

  if (items.length === 0) {
    const resolvedTitle =
      emptyTitle ??
      (hasActiveFilters
        ? "No memory items match the current filters."
        : "No memory items are stored yet.");

    const resolvedDetail =
      emptyDetail ??
      (hasActiveFilters
        ? "Clear or loosen filters to inspect a broader slice of memory."
        : "Once summary and item wiring are live, stored memory will appear here.");

    return (
      <ListStatePanel
        eyebrow="Memory list"
        title={resolvedTitle}
        detail={resolvedDetail}
        tone={hasActiveFilters ? "bronze" : "emerald"}
      />
    );
  }

  return (
    <section
      style={{
        display: "grid",
        gap: "0.9rem",
        minHeight: 0,
        flex: 1,
        overflowY: "auto",
        paddingRight: "0.15rem"
      }}
    >
      {showRoomTruthNote ? (
        <div
          style={{
            padding: "0.9rem 1rem",
            borderRadius: "16px",
            border: `1px solid ${palette.lineBronze}`,
            background:
              "linear-gradient(180deg, rgba(43, 31, 21, 0.34) 0%, rgba(18, 25, 37, 0.56) 100%)",
            color: palette.silverMuted,
            lineHeight: 1.55
          }}
        >
          This list is showing the currently visible memory slice. Item-level
          actions should only appear as truly live, not as decorative fake power.
        </div>
      ) : null}

      {items.map((item) => (
        <MemoryItemCard
          key={item.memoryId}
          item={item}
          actions={actions}
          onPin={onPin}
          onMove={onMove}
          onEdit={onEdit}
          onForget={onForget}
          onArchive={onArchive}
          onHistory={onHistory}
        />
      ))}
    </section>
  );
}

function ListStatePanel({
  eyebrow,
  title,
  detail,
  tone
}: {
  eyebrow: string;
  title: string;
  detail: string;
  tone: "teal" | "bronze" | "emerald";
}) {
  const toneColor =
    tone === "teal"
      ? palette.teal
      : tone === "emerald"
        ? palette.emerald
        : palette.bronze;

  return (
    <div
      style={{
        display: "grid",
        gap: "0.55rem",
        padding: "1.05rem 1.1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.78) 0%, rgba(11, 14, 18, 0.82) 100%)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)"
      }}
    >
      <div
        style={{
          fontSize: "0.78rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: toneColor
        }}
      >
        {eyebrow}
      </div>

      <div
        style={{
          color: palette.silver,
          fontSize: "1.02rem",
          fontWeight: 700,
          lineHeight: 1.35
        }}
      >
        {title}
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.6,
          maxWidth: "72ch"
        }}
      >
        {detail}
      </div>
    </div>
  );
}
