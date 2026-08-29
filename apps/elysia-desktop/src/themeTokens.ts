export type TrustTone =
  | "local"
  | "approval"
  | "blocked"
  | "external"
  | "degraded"
  | "inactive";

export type TrustBadge = {
  label: string;
  tone: TrustTone;
};

export const palette = {
  obsidian: "#0B0E12",
  midnight: "#121925",
  basalt: "#2A3138",
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.36)",
  glowTeal: "rgba(126, 215, 209, 0.16)",
  glowBronze: "rgba(138, 106, 60, 0.14)"
} as const;

export const shellTokens = {
  appBackground:
    "radial-gradient(circle at 18% 12%, rgba(126, 215, 209, 0.08), transparent 18%), radial-gradient(circle at 84% 9%, rgba(138, 106, 60, 0.08), transparent 20%), linear-gradient(180deg, #111726 0%, #0B0E12 100%)",
  etchedGrid:
    "linear-gradient(90deg, rgba(126, 215, 209, 0.05) 0, rgba(126, 215, 209, 0.05) 1px, transparent 1px, transparent 120px), linear-gradient(180deg, rgba(138, 106, 60, 0.035) 0, rgba(138, 106, 60, 0.035) 1px, transparent 1px, transparent 120px)",
  topBarBackground:
    "linear-gradient(180deg, rgba(18, 25, 37, 0.98) 0%, rgba(14, 19, 29, 0.96) 100%)",
  topBarTraceOverlay:
    "linear-gradient(120deg, transparent 0%, rgba(126, 215, 209, 0.08) 22%, transparent 24%, transparent 38%, rgba(138, 106, 60, 0.08) 41%, transparent 43%, transparent 60%, rgba(199, 210, 218, 0.06) 63%, transparent 65%)",
  topBarCardBackground:
    "linear-gradient(180deg, rgba(24, 33, 48, 0.78) 0%, rgba(18, 25, 37, 0.84) 100%)",
  statusBarBackground:
    "linear-gradient(180deg, rgba(16, 21, 31, 0.98) 0%, rgba(11, 14, 18, 1) 100%)",
  leftRailBackground:
    "linear-gradient(180deg, rgba(18, 25, 37, 0.96) 0%, rgba(11, 14, 18, 0.94) 100%)",
  rightDrawerBackground:
    "linear-gradient(180deg, rgba(18, 25, 37, 0.98) 0%, rgba(11, 14, 18, 0.94) 100%)",
  rightDrawerTrustSurfaceBackground:
    "linear-gradient(180deg, rgba(43, 31, 21, 0.46) 0%, rgba(18, 25, 37, 0.68) 100%)",
  rightDrawerSectionBackground:
    "linear-gradient(180deg, rgba(24, 33, 48, 0.64) 0%, rgba(18, 25, 37, 0.72) 100%)",
  rightDrawerStateBackground:
    "linear-gradient(180deg, rgba(18, 41, 43, 0.42) 0%, rgba(18, 25, 37, 0.74) 100%)",
  leftRailNoteBackground:
    "linear-gradient(180deg, rgba(43, 31, 21, 0.5) 0%, rgba(18, 25, 37, 0.62) 100%)",
  leftRailItemSelectedBackground:
    "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.76) 100%)",
  leftRailItemBackground:
    "linear-gradient(180deg, rgba(24, 33, 48, 0.44) 0%, rgba(18, 25, 37, 0.5) 100%)",
  workspaceBackground:
    "radial-gradient(circle at 16% 12%, rgba(126, 215, 209, 0.09), transparent 19%), radial-gradient(circle at 84% 18%, rgba(138, 106, 60, 0.08), transparent 18%), linear-gradient(180deg, rgba(18, 25, 37, 0.98) 0%, rgba(11, 14, 18, 0.98) 100%)",
  workspaceCardBackground:
    "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.82) 100%)",
  workspaceMiniCardBackground:
    "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.74) 100%)"
} as const;

export const trustToneTokens = {
  local: {
    text: palette.teal,
    border: "rgba(126, 215, 209, 0.38)",
    background: "rgba(18, 35, 38, 0.68)",
    glow: `0 0 0 1px rgba(126, 215, 209, 0.08), 0 0 22px ${palette.glowTeal}`,
    dot: palette.teal
  },
  approval: {
    text: palette.sandstone,
    border: "rgba(184, 162, 123, 0.34)",
    background: "rgba(44, 33, 21, 0.72)",
    glow: `0 0 0 1px rgba(184, 162, 123, 0.06), 0 0 18px ${palette.glowBronze}`,
    dot: palette.sandstone
  },
  blocked: {
    text: "#D99A7A",
    border: "rgba(139, 78, 47, 0.42)",
    background: "rgba(48, 23, 17, 0.74)",
    glow: "none",
    dot: "#C97855"
  },
  external: {
    text: palette.silver,
    border: "rgba(199, 210, 218, 0.22)",
    background: "rgba(34, 41, 51, 0.76)",
    glow: "none",
    dot: palette.silverMuted
  },
  degraded: {
    text: palette.bronze,
    border: "rgba(138, 106, 60, 0.42)",
    background: "rgba(40, 32, 23, 0.72)",
    glow: "none",
    dot: palette.bronze
  },
  inactive: {
    text: palette.silverMuted,
    border: palette.lineSilver,
    background: "rgba(35, 41, 49, 0.64)",
    glow: "none",
    dot: palette.silverMuted
  }
} as const satisfies Record<
  TrustTone,
  {
    text: string;
    border: string;
    background: string;
    glow: string;
    dot: string;
  }
>;

export const topBarTrustBadges: TrustBadge[] = [
  { label: "Local", tone: "local" },
  { label: "Approval needed", tone: "approval" },
  { label: "External sealed", tone: "external" },
  { label: "Blocked paths visible", tone: "blocked" }
];

export const bottomStatusBadges: TrustBadge[] = [
  { label: "Local", tone: "local" },
  { label: "Approval needed", tone: "approval" },
  { label: "Blocked paths visible", tone: "blocked" },
  { label: "External sealed", tone: "external" }
];
