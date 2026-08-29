import TrustLanguageBadge from "./TrustLanguageBadge";
import {
  palette,
  shellTokens,
  type TrustBadge
} from "./themeTokens";

type BottomStatusBarProps = {
  onOpenStatusMenu: () => void;
  statusSummaryText?: string;
  statusBadges?: TrustBadge[];
};

export const DEFAULT_BOTTOM_STATUS_BADGES: TrustBadge[] = [
  { label: "Local", tone: "local" },
  { label: "External sealed", tone: "external" }
];

const DEFAULT_STATUS_SUMMARY_TEXT =
  "Current trust posture for this chamber session.";

export default function BottomStatusBar({
  onOpenStatusMenu,
  statusSummaryText = DEFAULT_STATUS_SUMMARY_TEXT,
  statusBadges = DEFAULT_BOTTOM_STATUS_BADGES
}: BottomStatusBarProps) {
  const resolvedBadges =
    statusBadges.length > 0 ? statusBadges : DEFAULT_BOTTOM_STATUS_BADGES;

  return (
    <footer
      className="elysia-bottom-status"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) minmax(220px, 320px) max-content",
        alignItems: "center",
        gap: "0.58rem",
        padding: "0.2rem 1rem",
        background: shellTokens.statusBarBackground,
        borderTop: `1px solid ${palette.lineBronze}`,
        color: palette.silverMuted,
        fontSize: "0.8rem",
        minHeight: "46px",
        maxHeight: "46px",
        overflow: "hidden"
      }}
    >
      <div
        style={{
          minWidth: 0,
          fontSize: "0.8rem",
          lineHeight: 1.1,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis"
        }}
      >
        {statusSummaryText}
      </div>

      <button
        type="button"
        onClick={onOpenStatusMenu}
        style={{
          minWidth: 0,
          justifySelf: "center",
          width: "100%",
          maxWidth: "320px",
          padding: "0.22rem 0.6rem",
          borderRadius: "12px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.72) 0%, rgba(18, 25, 37, 0.78) 100%)",
          boxShadow:
            "0 0 0 1px rgba(199, 210, 218, 0.03), inset 0 1px 0 rgba(255,255,255,0.03)",
          overflow: "hidden",
          appearance: "none",
          cursor: "pointer",
          textAlign: "left",
          color: palette.silver
        }}
      >
        <div
          style={{
            fontSize: "0.5rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: palette.silverMuted,
            lineHeight: 1,
            marginBottom: "0.06rem",
            whiteSpace: "nowrap"
          }}
        >
          Status Menu
        </div>
        <div
          style={{
            fontSize: "0.56rem",
            letterSpacing: "0.005em",
            lineHeight: 1.05,
            color: palette.silver,
            whiteSpace: "nowrap"
          }}
        >
          Open trust center with chamber status & orientation surfaces
        </div>
      </button>

      <div
        style={{
          display: "flex",
          flexWrap: "nowrap",
          justifyContent: "flex-end",
          gap: "0.5rem",
          minWidth: 0,
          overflow: "hidden"
        }}
      >
        {resolvedBadges.map((badge) => (
          <TrustLanguageBadge
            key={`${badge.tone}-${badge.label}`}
            badge={badge}
            density="compact"
          />
        ))}
      </div>
    </footer>
  );
}
