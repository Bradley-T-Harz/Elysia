// Right Drawer is for compact live summary, not deep explanation.
// Deeper explanation belongs in Chamber and later full rooms.

import { useLayoutEffect, useRef } from "react";
import ElysiaPortraitCard from "./ElysiaPortraitCard";

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.36)",
  lineTeal: "rgba(126, 215, 209, 0.22)",
  bgCard:
    "linear-gradient(180deg, rgba(24, 33, 48, 0.64) 0%, rgba(18, 25, 37, 0.72) 100%)",
  bgCardWarm:
    "linear-gradient(180deg, rgba(43, 31, 21, 0.46) 0%, rgba(18, 25, 37, 0.68) 100%)"
} as const;

export type FeatureState =
  | "live"
  | "partial"
  | "planned"
  | "inactive"
  | "unavailable"
  | "degraded"
  | "blocked";

export type DrawerRow = {
  label: string;
  value: string;
};

type DrawerAccent = "warm" | "teal" | "default";

export type DrawerSection = {
  key: string;
  title: string;
  state: FeatureState;
  accent?: DrawerAccent;
  rows: DrawerRow[];
};

export const DEFAULT_RIGHT_DRAWER_SECTIONS: DrawerSection[] = [
  {
    key: "active_context",
    title: "Active Context",
    state: "partial",
    accent: "warm",
    rows: [
      { label: "Mode", value: "No active working mode is surfaced in idle chamber state" },
      { label: "Conversation", value: "No active conversation is loaded" },
      { label: "Context source", value: "Idle chamber state only" }
    ]
  },
  {
    key: "boundary_flags",
    title: "Boundary Flags",
    state: "live",
    accent: "teal",
    rows: [
      { label: "Local / external", value: "Current chamber state remains local" },
      { label: "Blocked / degraded", value: "No blocked or degraded path is active" },
      { label: "Posture", value: "Downstream of body truth only" }
    ]
  },
  {
    key: "approval_needed",
    title: "Approval Needed",
    state: "inactive",
    rows: [
      { label: "Current state", value: "No approval required" },
      { label: "Blocked state", value: "Approval is shown only when a request is gated" }
    ]
  },
  {
    key: "request_trace",
    title: "Request Trace",
    state: "partial",
    rows: [
      { label: "Current trace", value: "No active trace" },
      { label: "Status", value: "Idle summary only; richer trace surfacing is still maturing" }
    ]
  }
];

function getStateColors(state: FeatureState) {
  switch (state) {
    case "live":
      return {
        border: "rgba(126, 215, 209, 0.32)",
        text: palette.teal,
        background: "rgba(126, 215, 209, 0.08)"
      };
    case "partial":
      return {
        border: "rgba(184, 162, 123, 0.34)",
        text: palette.sandstone,
        background: "rgba(184, 162, 123, 0.1)"
      };
    case "planned":
      return {
        border: "rgba(199, 210, 218, 0.22)",
        text: palette.silverMuted,
        background: "rgba(199, 210, 218, 0.08)"
      };
    case "inactive":
      return {
        border: "rgba(199, 210, 218, 0.18)",
        text: palette.silverMuted,
        background: "rgba(199, 210, 218, 0.06)"
      };
    case "unavailable":
      return {
        border: "rgba(199, 210, 218, 0.22)",
        text: "#D8A5A5",
        background: "rgba(216, 165, 165, 0.08)"
      };
    case "degraded":
      return {
        border: "rgba(215, 169, 126, 0.3)",
        text: "#D7A97E",
        background: "rgba(215, 169, 126, 0.08)"
      };
    case "blocked":
      return {
        border: "rgba(189, 115, 115, 0.34)",
        text: "#D69494",
        background: "rgba(189, 115, 115, 0.08)"
      };
    default:
      return {
        border: palette.lineSilver,
        text: palette.silverMuted,
        background: "rgba(199, 210, 218, 0.06)"
      };
  }
}

function SectionStateBadge({ state }: { state: FeatureState }) {
  const colors = getStateColors(state);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "0.16rem 0.45rem",
        borderRadius: "999px",
        border: `1px solid ${colors.border}`,
        background: colors.background,
        color: colors.text,
        fontSize: "0.66rem",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        whiteSpace: "nowrap"
      }}
    >
      {state}
    </span>
  );
}

function DrawerSectionCard({ section }: { section: DrawerSection }) {
  const borderColor =
    section.accent === "warm"
      ? palette.lineBronze
      : section.accent === "teal"
        ? palette.lineTeal
        : palette.lineSilver;

  const background =
    section.accent === "warm" ? palette.bgCardWarm : palette.bgCard;

  const titleColor =
    section.accent === "warm"
      ? palette.bronze
      : section.accent === "teal"
        ? palette.teal
        : palette.silverMuted;

  return (
    <details
      open={section.state !== "planned"}
      data-drawer-state={section.state}
      style={{
        padding: "0.74rem 0.8rem",
        borderRadius: "16px",
        border: `1px solid ${borderColor}`,
        background
      }}
    >
      <summary
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "0.7rem",
          marginBottom: "0.52rem",
          cursor: "pointer",
          listStyle: "none"
        }}
      >
        <div
          style={{
            fontSize: "0.72rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: titleColor
          }}
        >
          {section.title}
        </div>

        <SectionStateBadge state={section.state} />
      </summary>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.38rem"
        }}
      >
        {section.rows.map((row) => (
          <div
            key={`${section.key}-${row.label}`}
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 104px) minmax(0, 1fr)",
              gap: "0.48rem",
              alignItems: "start"
            }}
          >
            <div
              style={{
                color: palette.sandstone,
                fontSize: "0.74rem",
                lineHeight: 1.35
              }}
            >
              {row.label}
            </div>
            <div
              style={{
                color: palette.silver,
                fontSize: "0.74rem",
                lineHeight: 1.45
              }}
            >
              {row.value}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

// Right drawer scrolls internally so trust/context remains usable
// under smaller window heights without moving the portrait block.

export type RightDrawerLayoutMode = "fill" | "content";

export type RightDrawerProps = {
  sections?: DrawerSection[];
  layoutMode?: RightDrawerLayoutMode;
  onOpenQuickInvoke?: () => void;
};

export default function RightDrawer({
  sections = DEFAULT_RIGHT_DRAWER_SECTIONS,
  layoutMode = "fill",
  onOpenQuickInvoke
}: RightDrawerProps) {
  const resolvedSections = sections;
  const isContentMode = layoutMode === "content";
  const scrollRegionRef = useRef<HTMLDivElement | null>(null);
  const previousLayoutModeRef = useRef<RightDrawerLayoutMode>(layoutMode);

  useLayoutEffect(() => {
    const scrollRegion = scrollRegionRef.current;
    const enteredContentMode =
      previousLayoutModeRef.current !== "content" && layoutMode === "content";

    if (scrollRegion && enteredContentMode) {
      scrollRegion.scrollTop = 0;
    }

    previousLayoutModeRef.current = layoutMode;
  }, [layoutMode]);

  return (
    <aside
      className="elysia-right-drawer"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.82rem",
        padding: "0.92rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.98) 0%, rgba(11, 14, 18, 0.94) 100%)",
        boxShadow:
          "inset 0 1px 0 rgba(255,255,255,0.03), 0 8px 24px rgba(0,0,0,0.22)",
        width: "100%",
        boxSizing: "border-box",
        minHeight: 0,
        height: isContentMode ? "auto" : "100%",
        maxHeight: isContentMode ? "none" : "100%",
        flex: isContentMode ? "0 0 auto" : 1,
        overflow: "hidden"
      }}
    >
      {/* Portrait owns the visible launcher surface.
          RightDrawer only passes the shell callback through. */}
      <ElysiaPortraitCard
        sticky
        onOpenQuickInvoke={onOpenQuickInvoke}
      />

      <div
        ref={scrollRegionRef}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.82rem",
          flex: isContentMode ? "0 1 auto" : 1,
          minHeight: 0,
          overflowY: "auto",
          overscrollBehavior: "contain",
          scrollbarGutter: "stable",
          paddingRight: "0.15rem",
          paddingBottom: isContentMode ? "0.35rem" : "0.72rem",
          scrollPaddingBottom: isContentMode ? "0.35rem" : "0.72rem"
        }}
      >
        <div
          style={{
            paddingInline: "0.15rem"
          }}
        >
          <div
            style={{
              fontSize: "0.76rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.28rem"
            }}
          >
            Right Drawer
          </div>
          <div
            style={{
              color: palette.silverMuted,
              lineHeight: 1.55,
              fontSize: "0.8rem"
            }}
          >
            Live inspection stays here. Compact, current, and downstream of chamber truth.
          </div>
        </div>

        {resolvedSections.map((section) => (
          <DrawerSectionCard key={section.key} section={section} />
        ))}
      </div>
    </aside>
  );
}
