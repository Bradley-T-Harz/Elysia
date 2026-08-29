import { useEffect, useState } from "react";
import type {
  DesktopStartupRoom,
  LeftRailDefaultBehavior
} from "./desktopPreferences";

export type LeftRailRoom = DesktopStartupRoom | "admin";

type LeftRailProps = {
  activeRoom: LeftRailRoom | "status_menu";
  onSelectRoom: (room: LeftRailRoom) => void;
  defaultGroupBehavior?: LeftRailDefaultBehavior;
  showAdmin?: boolean;
};

type LeftRailItem = {
  kind: "room";
  room: LeftRailRoom;
  label: string;
  note: string;
  tone: "teal" | "bronze";
};

type LeftRailGroupId = "workrooms" | "memory_identity" | "control_system";

type LeftRailGroup = {
  id: LeftRailGroupId;
  label: string;
  rooms: LeftRailRoom[];
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.36)",
  glowTeal: "rgba(126, 215, 209, 0.16)"
} as const;

const leftRailItems: LeftRailItem[] = [
  {
    kind: "room",
    room: "projects",
    label: "Projects",
    note: "Project index and continuity room.",
    tone: "bronze"
  },
  {
    kind: "room",
    room: "admin",
    label: "Admin",
    note: "Installation governance without private-content authority.",
    tone: "bronze"
  },
  {
    kind: "room",
    room: "artifacts",
    label: "Artifacts",
    note: "Local generated outputs and safe previews.",
    tone: "bronze"
  },
  {
    kind: "room",
    room: "home",
    label: "Chamber",
    note: "Boot page and startup truth.",
    tone: "bronze"
  },
  {
    kind: "room",
    room: "conversations",
    label: "Conversations",
    note: "Enter the first working room.",
    tone: "teal"
  },
  {
    kind: "room",
    room: "memory",
    label: "Memory",
    note: "Inspectable continuity and memory governance.",
    tone: "teal"
  },
  {
    kind: "room",
    room: "governance",
    label: "Governance",
    note: "Rules of the house, trust zones, and control truth.",
    tone: "bronze"
  },
  {
    kind: "room",
    room: "requests",
    label: "Requests",
    note: "Inspectable request ledger and trace truth.",
    tone: "bronze"
  },
  {
    kind: "room",
    room: "addons",
    label: "Add-ons",
    note: "Marketplace-gated catalog and preview room.",
    tone: "bronze"
  },
  {
    kind: "room",
    room: "capabilities",
    label: "Capabilities",
    note: "Truth map of Elysia's available limbs.",
    tone: "teal"
  },
  {
    kind: "room",
    room: "health",
    label: "Health",
    note: "Local organism health and subsystem truth.",
    tone: "teal"
  },
  {
    kind: "room",
    room: "user_profile",
    label: "Personal Identity",
    note: "Sealed local identity and private user portfolio.",
    tone: "bronze"
  }
];

const chamberRoomId: LeftRailRoom = "home";

const leftRailGroups: LeftRailGroup[] = [
  {
    id: "workrooms",
    label: "Workrooms",
    rooms: ["conversations", "projects", "artifacts", "requests"]
  },
  {
    id: "memory_identity",
    label: "Memory & Identity",
    rooms: ["memory", "user_profile"]
  },
  {
    id: "control_system",
    label: "Control & System",
    rooms: ["governance", "capabilities", "addons", "health", "admin"]
  }
];

function buildDefaultOpenGroups(
  behavior: LeftRailDefaultBehavior,
  activeRoom: LeftRailRoom | "status_menu"
): Record<LeftRailGroupId, boolean> {
  const openByDefault = behavior === "expanded";
  const groups = {
    workrooms: openByDefault,
    memory_identity: openByDefault,
    control_system: openByDefault
  };
  const activeGroup = leftRailGroups.find((group) =>
    group.rooms.some((room) => room === activeRoom)
  );

  if (activeGroup) {
    groups[activeGroup.id] = true;
  }

  return groups;
}

function getLeftRailItem(room: LeftRailRoom): LeftRailItem {
  const item = leftRailItems.find((candidate) => candidate.room === room);

  if (!item) {
    throw new Error(`Missing left rail room definition for ${room}.`);
  }

  return item;
}

function getRoomDotColor(tone: "teal" | "bronze", selected: boolean) {
  if (selected) {
    return palette.teal;
  }

  return tone === "teal" ? palette.teal : palette.bronze;
}

type RoomButtonProps = {
  item: LeftRailItem;
  selected: boolean;
  onSelectRoom: (room: LeftRailRoom) => void;
};

function RoomButton({ item, selected, onSelectRoom }: RoomButtonProps) {
  const labelId = `left-rail-room-${item.room}-label`;
  const noteId = `left-rail-room-${item.room}-note`;

  return (
    <button
      type="button"
      onClick={() => onSelectRoom(item.room)}
      aria-current={selected ? "page" : undefined}
      aria-labelledby={labelId}
      aria-describedby={noteId}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.62rem",
        width: "100%",
        padding: "0.68rem 0.8rem",
        borderRadius: "13px",
        border: selected
          ? `1px solid rgba(126, 215, 209, 0.34)`
          : `1px solid rgba(199, 210, 218, 0.08)`,
        background: selected
          ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.76) 100%)"
          : "linear-gradient(180deg, rgba(24, 33, 48, 0.44) 0%, rgba(18, 25, 37, 0.5) 100%)",
        color: selected ? palette.teal : palette.silverMuted,
        boxShadow: selected ? `0 0 24px ${palette.glowTeal}` : "none",
        cursor: "pointer",
        textAlign: "left"
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: "0.52rem",
          height: "0.52rem",
          borderRadius: "999px",
          background: getRoomDotColor(item.tone, selected),
          opacity: selected ? 1 : 0.82,
          flexShrink: 0
        }}
      />
      <span style={{ display: "grid", gap: "0.14rem", minWidth: 0 }}>
        <span id={labelId} style={{ fontWeight: selected ? 700 : 600 }}>
          {item.label}
        </span>
        <span
          id={noteId}
          style={{
            fontSize: "0.76rem",
            color: palette.silverMuted,
            lineHeight: 1.28
          }}
        >
          {item.note}
        </span>
      </span>
    </button>
  );
}

export default function LeftRail({
  activeRoom,
  onSelectRoom,
  defaultGroupBehavior = "collapsed",
  showAdmin = false
}: LeftRailProps) {
  const [openGroups, setOpenGroups] = useState<
    Record<LeftRailGroupId, boolean>
  >(() => buildDefaultOpenGroups(defaultGroupBehavior, activeRoom));

  useEffect(() => {
    setOpenGroups(buildDefaultOpenGroups(defaultGroupBehavior, activeRoom));
  }, [defaultGroupBehavior]);

  useEffect(() => {
    const activeGroup = leftRailGroups.find((group) =>
      group.rooms.some((room) => room === activeRoom)
    );

    if (!activeGroup) {
      return;
    }

    setOpenGroups((current) => {
      if (current[activeGroup.id]) {
        return current;
      }

      return { ...current, [activeGroup.id]: true };
    });
  }, [activeRoom]);

  const chamberItem = getLeftRailItem(chamberRoomId);

  return (
    <aside
      className="elysia-left-rail"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.78rem",
        minHeight: 0,
        padding: "0.78rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.96) 0%, rgba(11, 14, 18, 0.94) 100%)",
        boxShadow:
          "inset 0 1px 0 rgba(255,255,255,0.03), 0 8px 24px rgba(0,0,0,0.22)",
        overflowY: "auto"
      }}
    >
      <div>
        <div
          style={{
            fontSize: "0.72rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: palette.sandstone,
            marginBottom: "0.28rem"
          }}
        >
          Rooms
        </div>
        <div style={{ color: palette.silverMuted, lineHeight: 1.425 }}>
          Move between chamber surfaces.
        </div>
      </div>

      <nav aria-label="Rooms" style={{ display: "grid", gap: "0.72rem" }}>
        <RoomButton
          item={chamberItem}
          selected={activeRoom === chamberRoomId}
          onSelectRoom={onSelectRoom}
        />

        {leftRailGroups.map((group) => {
          const groupIsOpen = openGroups[group.id];
          const groupHeaderId = `left-rail-${group.id}-heading`;
          const groupContentId = `left-rail-${group.id}-rooms`;

          return (
            <div key={group.id} style={{ display: "grid", gap: "0.42rem" }}>
              <button
                id={groupHeaderId}
                type="button"
                aria-expanded={groupIsOpen}
                aria-controls={groupContentId}
                onClick={() =>
                  setOpenGroups((current) => ({
                    ...current,
                    [group.id]: !current[group.id]
                  }))
                }
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  width: "100%",
                  padding: "0.2rem 0.22rem",
                  border: 0,
                  background: "transparent",
                  color: palette.sandstone,
                  cursor: "pointer",
                  fontSize: "0.69rem",
                  fontWeight: 700,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  textAlign: "left"
                }}
              >
                <span>{group.label}</span>
                <span
                  aria-hidden="true"
                  style={{
                    color: palette.silverMuted,
                    fontSize: "0.78rem",
                    transform: groupIsOpen ? "rotate(0deg)" : "rotate(-90deg)",
                    transition: "transform 140ms ease"
                  }}
                >
                  ▾
                </span>
              </button>

              <div
                id={groupContentId}
                role="group"
                aria-labelledby={groupHeaderId}
                hidden={!groupIsOpen}
                style={{
                  display: groupIsOpen ? "grid" : undefined,
                  gap: "0.46rem"
                }}
              >
                {group.rooms.filter((room) => room !== "admin" || showAdmin).map((room) => {
                  const item = getLeftRailItem(room);

                  return (
                    <RoomButton
                      key={item.room}
                      item={item}
                      selected={activeRoom === item.room}
                      onSelectRoom={onSelectRoom}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      <div
        style={{
          marginTop: "auto",
          padding: "0.9rem",
          borderRadius: "15px",
          border: `1px solid ${palette.lineBronze}`,
          background:
            "linear-gradient(180deg, rgba(43, 31, 21, 0.5) 0%, rgba(18, 25, 37, 0.62) 100%)"
        }}
      >
        <div
          style={{
            fontSize: "0.74rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.bronze,
            marginBottom: "0.35rem"
          }}
        >
          House posture
        </div>
        <div style={{ color: palette.silverMuted, lineHeight: 1.5 }}>
          Local-first, calm, and bounded. Working rooms should only show power
          the body actually has.
        </div>
      </div>
    </aside>
  );
}
