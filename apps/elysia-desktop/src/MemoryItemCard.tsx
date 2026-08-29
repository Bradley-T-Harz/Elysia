import MemoryClassBadge from "./MemoryClassBadge";
import MemorySensitivityBadge from "./MemorySensitivityBadge";
import MemoryMutabilityBadge from "./MemoryMutabilityBadge";

export type MemoryItemCardFlagSet = {
  pinned?: boolean;
  userDeclared?: boolean;
  inferred?: boolean;
  verified?: boolean;
  stale?: boolean;
};

export type MemoryItemCardData = {
  memoryId: string;

  title: string;
  bodyExcerpt: string;
  whyStored: string;

  memoryClass:
    | "working"
    | "conversation"
    | "project"
    | "research"
    | "operational"
    | "preference"
    | "sealed_private"
    | "audit";

  sensitivity: "public" | "internal" | "private" | "sealed";

  mutability:
    | "live_editable"
    | "append_only"
    | "review_required"
    | "immutable"
    | "not_yet_live";

  status:
    | "active"
    | "provisional"
    | "archived"
    | "superseded"
    | "blocked";

  sourceLabel: string;
  sourceKind?: string;

  createdAtLabel?: string;
  updatedAtLabel: string;

  projectLabel?: string;
  conversationLabel?: string;

  flags?: MemoryItemCardFlagSet;
};

export type MemoryItemCardActionAvailability = {
  canPin?: boolean;
  canMove?: boolean;
  canEdit?: boolean;
  canForget?: boolean;
};

export type MemoryItemCardProps = {
  item: MemoryItemCardData;
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
  panelRaised: "rgba(24, 33, 48, 0.74)",
  panelInset: "rgba(11, 14, 18, 0.42)"
} as const;

type ActionMode = "live" | "planned" | "hidden";

export default function MemoryItemCard({
  item,
  actions,
  onPin,
  onMove,
  onEdit,
  onForget,
  onArchive,
  onHistory
}: MemoryItemCardProps) {
  const pinMode = getActionMode(actions?.canPin, onPin);
  const moveMode = getActionMode(actions?.canMove, onMove);
  const editMode = getActionMode(actions?.canEdit, onEdit);
  const forgetMode = getActionMode(actions?.canForget, onForget);
  const archiveMode: ActionMode = onArchive ? "live" : "hidden";
  const historyMode: ActionMode = onHistory ? "live" : "hidden";

  const visibleActionCount = [pinMode, moveMode, editMode, archiveMode, historyMode, forgetMode].filter(
    (mode) => mode !== "hidden"
  ).length;

  const title = item.title.trim() || "Untitled memory";

  return (
    <article
      style={{
        display: "grid",
        gap: "0.9rem",
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.74) 100%)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)"
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "1rem"
        }}
      >
        <div style={{ minWidth: 0, display: "grid", gap: "0.38rem" }}>
          <h3
            style={{
              margin: 0,
              fontSize: "1.05rem",
              lineHeight: 1.25,
              color: palette.silver,
              overflowWrap: "anywhere"
            }}
          >
            {title}
          </h3>

          <div
            style={{
              color: palette.silverMuted,
              fontSize: "0.85rem",
              lineHeight: 1.45,
              display: "flex",
              gap: "0.7rem",
              flexWrap: "wrap"
            }}
          >
            <span>Source: {item.sourceLabel}</span>
            <span>Updated: {item.updatedAtLabel}</span>
            {item.createdAtLabel ? <span>Created: {item.createdAtLabel}</span> : null}
          </div>
        </div>

        {item.flags?.pinned ? (
          <span
            style={{
              flexShrink: 0,
              padding: "0.35rem 0.6rem",
              borderRadius: "999px",
              border: `1px solid ${palette.lineBronze}`,
              background: "rgba(43, 31, 21, 0.42)",
              color: palette.silver,
              fontSize: "0.76rem",
              fontWeight: 700,
              letterSpacing: "0.04em",
              textTransform: "uppercase"
            }}
          >
            Pinned
          </span>
        ) : null}
      </header>

      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap"
        }}
      >
        <MemoryClassBadge value={item.memoryClass} />
        <MemorySensitivityBadge value={item.sensitivity} />
        <MemoryMutabilityBadge value={item.mutability} />
        <Pill tone={getStatusTone(item.status)} label={formatStatus(item.status)} />
      </div>

      <section
        style={{
          padding: "0.85rem 0.9rem",
          borderRadius: "14px",
          border: `1px solid ${palette.lineSilver}`,
          background: "rgba(11, 14, 18, 0.32)"
        }}
      >
        <div
          style={{
            color: palette.silver,
            lineHeight: 1.65,
            whiteSpace: "pre-wrap",
            overflow: "hidden"
          }}
        >
          {item.bodyExcerpt}
        </div>
      </section>

      <div
        style={{
          display: "flex",
          gap: "0.7rem",
          flexWrap: "wrap",
          color: palette.silverMuted,
          fontSize: "0.85rem",
          lineHeight: 1.45
        }}
      >
        {item.sourceKind ? <MetaChip label={`Kind: ${item.sourceKind}`} /> : null}
        {item.projectLabel ? <MetaChip label={`Project: ${item.projectLabel}`} /> : null}
        {item.conversationLabel ? (
          <MetaChip label={`Conversation: ${item.conversationLabel}`} />
        ) : null}
      </div>

      <section
        style={{
          display: "grid",
          gap: "0.4rem"
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
          Why stored
        </div>
        <div
          style={{
            color: palette.silverMuted,
            lineHeight: 1.6
          }}
        >
          {item.whyStored}
        </div>
      </section>

      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap"
        }}
      >
        {item.flags?.userDeclared ? <FlagChip label="User-declared" /> : null}
        {item.flags?.inferred ? <FlagChip label="Inferred" /> : null}
        {item.flags?.verified ? <FlagChip label="Verified" /> : null}
        {item.flags?.stale ? <FlagChip label="Stale" /> : null}
      </div>

      {visibleActionCount > 0 ? (
        <div
          style={{
            display: "flex",
            gap: "0.65rem",
            flexWrap: "wrap",
            paddingTop: "0.2rem",
            borderTop: `1px solid ${palette.lineSilver}`
          }}
        >
          <ActionButton
            label="Pin"
            mode={pinMode}
            onClick={onPin ? () => onPin(item.memoryId) : undefined}
          />
          <ActionButton
            label="Move"
            mode={moveMode}
            onClick={onMove ? () => onMove(item.memoryId) : undefined}
          />
          <ActionButton
            label="Edit"
            mode={editMode}
            onClick={onEdit ? () => onEdit(item.memoryId) : undefined}
          />
          <ActionButton
            label={item.status === "archived" ? "Restore" : "Archive"}
            mode={archiveMode}
            onClick={onArchive ? () => onArchive(item.memoryId) : undefined}
          />
          <ActionButton
            label="History"
            mode={historyMode}
            onClick={onHistory ? () => onHistory(item.memoryId) : undefined}
          />
          <ActionButton
            label="Forget"
            mode={forgetMode}
            onClick={onForget ? () => onForget(item.memoryId) : undefined}
          />
        </div>
      ) : null}
    </article>
  );
}

function Pill({
  label,
  tone
}: {
  label: string;
  tone: "teal" | "bronze" | "emerald" | "oxide" | "silver";
}) {
  const toneMap = {
    teal: {
      border: palette.lineTeal,
      background: "rgba(16, 41, 43, 0.34)",
      color: palette.teal
    },
    bronze: {
      border: palette.lineBronze,
      background: "rgba(43, 31, 21, 0.34)",
      color: palette.sandstone
    },
    emerald: {
      border: "rgba(47, 138, 104, 0.30)",
      background: "rgba(20, 42, 34, 0.34)",
      color: palette.emerald
    },
    oxide: {
      border: "rgba(139, 78, 47, 0.34)",
      background: "rgba(43, 27, 20, 0.34)",
      color: "#D89A77"
    },
    silver: {
      border: palette.lineSilver,
      background: "rgba(24, 33, 48, 0.34)",
      color: palette.silver
    }
  } as const;

  const colors = toneMap[tone];

  return (
    <span
      style={{
        padding: "0.38rem 0.65rem",
        borderRadius: "999px",
        border: `1px solid ${colors.border}`,
        background: colors.background,
        color: colors.color,
        fontSize: "0.76rem",
        fontWeight: 700,
        letterSpacing: "0.04em",
        textTransform: "uppercase"
      }}
    >
      {label}
    </span>
  );
}

function MetaChip({ label }: { label: string }) {
  return (
    <span
      style={{
        padding: "0.35rem 0.6rem",
        borderRadius: "999px",
        border: `1px solid ${palette.lineSilver}`,
        background: palette.panelInset,
        color: palette.silverMuted
      }}
    >
      {label}
    </span>
  );
}

function FlagChip({ label }: { label: string }) {
  return (
    <span
      style={{
        padding: "0.35rem 0.6rem",
        borderRadius: "999px",
        border: `1px dashed ${palette.lineBronze}`,
        background: "rgba(43, 31, 21, 0.18)",
        color: palette.silverMuted,
        fontSize: "0.78rem"
      }}
    >
      {label}
    </span>
  );
}

function ActionButton({
  label,
  mode,
  onClick
}: {
  label: string;
  mode: ActionMode;
  onClick?: () => void;
}) {
  if (mode === "hidden") {
    return null;
  }

  const isLive = mode === "live";

  return (
    <button
      type="button"
      onClick={isLive ? onClick : undefined}
      disabled={!isLive}
      style={{
        padding: "0.72rem 0.95rem",
        borderRadius: "12px",
        border: `1px solid ${
          isLive ? palette.lineTeal : palette.lineBronze
        }`,
        background: isLive
          ? "linear-gradient(180deg, rgba(16, 41, 43, 0.46) 0%, rgba(24, 33, 48, 0.56) 100%)"
          : "linear-gradient(180deg, rgba(43, 31, 21, 0.24) 0%, rgba(24, 33, 48, 0.34) 100%)",
        color: isLive ? palette.silver : palette.silverMuted,
        cursor: isLive ? "pointer" : "not-allowed",
        opacity: isLive ? 1 : 0.78
      }}
      title={isLive ? `${label} is live.` : `${label} is not live yet.`}
    >
      {isLive ? label : `${label} (planned)`}
    </button>
  );
}

function getActionMode(
  available: boolean | undefined,
  handler: unknown
): ActionMode {
  if (available === false) {
    return "hidden";
  }

  if (available === true) {
    return typeof handler === "function" ? "live" : "planned";
  }

  return typeof handler === "function" ? "live" : "hidden";
}

function formatStatus(value: MemoryItemCardData["status"]) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getStatusTone(
  status: MemoryItemCardData["status"]
): "teal" | "bronze" | "emerald" | "oxide" | "silver" {
  switch (status) {
    case "active":
      return "teal";
    case "provisional":
      return "bronze";
    case "archived":
      return "silver";
    case "superseded":
      return "oxide";
    case "blocked":
      return "oxide";
  }
}
