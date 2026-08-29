import { useState } from "react";

export type MessageBubbleMessage = {
  messageId: string;
  conversationId: string | null;
  role: string;
  content: string;
  createdAtUtc: string | null;
  requestId: string | null;
  invocationStatus: string | null;
  responseSource: string | null;
  selectedRole: string | null;
  selectedRuntime: string | null;
  selectedModelRuntimeTag: string | null;
  usedFallback: boolean | null;
  fallbackFrom: string | null;
  fallbackTo: string | null;
  approvalNeeded: boolean | null;
  approvalState: string | null;
  localityState: string | null;
  capabilityState: string | null;
  blocked: boolean | null;
  degraded: boolean | null;
  error: string | null;
  warnings: string[];
  caveats: string[];
};

type MessageBubbleProps = {
  message: MessageBubbleMessage;
  isLatestAssistantMessage?: boolean;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  glowTeal: "rgba(126, 215, 209, 0.14)"
} as const;

const LONG_MESSAGE_CHARACTER_THRESHOLD = 1_000;
const LONG_MESSAGE_LINE_THRESHOLD = 14;
const COLLAPSED_MESSAGE_MAX_HEIGHT = "16rem";

function formatTimestamp(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function buildMetaItems(message: MessageBubbleMessage): string[] {
  const items: string[] = [];
  const fromAssistant = message.role === "assistant";

  const timestamp = formatTimestamp(message.createdAtUtc);
  if (timestamp) {
    items.push(timestamp);
  }

  if (!fromAssistant) {
    return items;
  }

  if (message.selectedRole) {
    items.push(`Role ${message.selectedRole}`);
  }

  if (message.selectedRuntime) {
    items.push(`Runtime ${message.selectedRuntime}`);
  }

  if (message.selectedModelRuntimeTag) {
    items.push(message.selectedModelRuntimeTag);
  }

  if (message.localityState) {
    items.push(
      message.localityState === "local"
        ? "Local"
        : `Locality ${message.localityState}`
    );
  }

  if (message.approvalNeeded === true || message.approvalState === "needed") {
    items.push("Approval needed");
  }

  if (message.usedFallback === true) {
    items.push("Fallback used");
  }

  if (message.blocked === true) {
    items.push("Blocked");
  }

  if (message.degraded === true) {
    items.push("Degraded");
  }

  return items;
}

function shouldShowDetailPanel(message: MessageBubbleMessage): boolean {
  if (message.role !== "assistant") {
    return false;
  }

  return Boolean(message.error) || message.blocked === true || message.degraded === true;
}

export default function MessageBubble({
  message,
  isLatestAssistantMessage = false
}: MessageBubbleProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const fromUser = message.role === "user";
  const metaItems = buildMetaItems(message);
  const showDetailPanel = shouldShowDetailPanel(message);
  const isLongMessage =
    message.content.length > LONG_MESSAGE_CHARACTER_THRESHOLD ||
    message.content.split(/\r?\n/).length > LONG_MESSAGE_LINE_THRESHOLD;
  const isCollapsed = isLongMessage && !isExpanded;
  const contentId = `conversation-message-${encodeURIComponent(message.messageId)}`;

  return (
    <div
      style={{
        alignSelf: fromUser ? "flex-end" : "stretch",
        width: fromUser ? "auto" : "100%",
        maxWidth: fromUser ? "min(88%, 72ch)" : "100%",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        gap: "0.45rem",
        padding: "0.9rem 1rem",
        borderRadius: fromUser ? "18px 18px 6px 18px" : "18px 18px 18px 6px",
        border: `1px solid ${
          fromUser ? "rgba(126, 215, 209, 0.22)" : "rgba(199, 210, 218, 0.10)"
        }`,
        background: fromUser
          ? "linear-gradient(180deg, rgba(16, 41, 43, 0.56) 0%, rgba(18, 25, 37, 0.74) 100%)"
          : "linear-gradient(180deg, rgba(24, 33, 48, 0.68) 0%, rgba(18, 25, 37, 0.78) 100%)",
        boxShadow: isLatestAssistantMessage ? `0 0 18px ${palette.glowTeal}` : "none"
      }}
    >
      <div
        style={{
          fontSize: "0.76rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: fromUser ? palette.teal : palette.sandstone,
          marginBottom: "0.1rem"
        }}
      >
        {message.role}
      </div>

      <div style={{ position: "relative", minWidth: 0 }}>
        <div
          id={contentId}
          style={{
            color: palette.silver,
            lineHeight: 1.62,
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            maxHeight: isCollapsed ? COLLAPSED_MESSAGE_MAX_HEIGHT : "none",
            overflow: isCollapsed ? "hidden" : "visible"
          }}
        >
          {message.content}
        </div>

        {isCollapsed && (
          <div
            aria-hidden="true"
            style={{
              position: "absolute",
              right: 0,
              bottom: 0,
              left: 0,
              height: "4.5rem",
              pointerEvents: "none",
              background:
                "linear-gradient(180deg, rgba(18, 25, 37, 0) 0%, rgba(18, 25, 37, 0.98) 100%)"
            }}
          />
        )}
      </div>

      {isLongMessage && (
        <button
          type="button"
          aria-expanded={isExpanded}
          aria-controls={contentId}
          onClick={() => setIsExpanded((current) => !current)}
          style={{
            alignSelf: "flex-start",
            minHeight: "2.35rem",
            padding: "0.48rem 0.72rem",
            borderRadius: "999px",
            border: `1px solid ${palette.lineBronze}`,
            background: "rgba(11, 14, 18, 0.42)",
            color: palette.sandstone,
            cursor: "pointer",
            fontSize: "0.8rem",
            fontWeight: 700
          }}
        >
          {isExpanded ? "Collapse message" : "Show full message"}
        </button>
      )}

      {metaItems.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: "0.55rem",
            flexWrap: "wrap",
            marginTop: "0.25rem",
            color: palette.silverMuted,
            fontSize: "0.76rem"
          }}
        >
          {metaItems.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      )}

      {showDetailPanel && (
        <div
          style={{
            marginTop: "0.25rem",
            padding: "0.7rem 0.8rem",
            borderRadius: "12px",
            border: `1px solid ${palette.lineBronze}`,
            background: "rgba(11, 14, 18, 0.42)",
            color: palette.silverMuted,
            lineHeight: 1.55
          }}
        >
          {message.blocked === true && !message.error && (
            <div>This response was blocked by the current governed boundary posture.</div>
          )}

          {message.degraded === true && !message.error && (
            <div>This response completed in a degraded path.</div>
          )}

          {message.error && <div>Error: {message.error}</div>}

          {message.warnings.map((warning) => (
            <div key={warning}>Warning: {warning}</div>
          ))}

          {message.caveats.map((caveat) => (
            <div key={caveat}>Caveat: {caveat}</div>
          ))}
        </div>
      )}
    </div>
  );
}
