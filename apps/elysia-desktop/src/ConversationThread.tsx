import type { ReactNode } from "react";
import MessageBubble from "./MessageBubble";

type ThreadState = "idle" | "loading" | "ready" | "error";
type ThreadNoticeTone = "info" | "degraded" | "blocked" | null;

export type ConversationThreadMessage = {
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

export type ConversationThreadData = {
  conversationId: string | null;
  title: string;
  displayTitle: string;
  preview: string | null;
  updatedAtUtc: string | null;
  messageCount: number;
  currentMode: string | null;
  currentRole: string | null;
  capabilityState: string | null;
  locality: string | null;
  approvalState: string | null;
  lastMessageRole: string | null;
  messages: ConversationThreadMessage[];
};

type ConversationThreadProps = {
  thread: ConversationThreadData | null;
  threadState: ThreadState;
  threadError: string | null;
  threadNotice: string | null;
  threadNoticeTone?: ThreadNoticeTone;
  latestAssistantMessageId?: string | null;
  transientPanel?: ReactNode;
  finalNotice?: string | null;
  finalNoticeTone?: ThreadNoticeTone;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  lineTeal: "rgba(126, 215, 209, 0.24)"
} as const;

const THREAD_COLUMN_MAX_WIDTH_PX = 920;

function getNoticeStyles(tone: ThreadNoticeTone) {
  if (tone === "blocked") {
    return {
      border: "1px solid rgba(139, 78, 47, 0.34)",
      background:
        "linear-gradient(180deg, rgba(48, 23, 17, 0.52) 0%, rgba(18, 25, 37, 0.72) 100%)"
    };
  }

  if (tone === "degraded") {
    return {
      border: "1px solid rgba(184, 162, 123, 0.24)",
      background:
        "linear-gradient(180deg, rgba(43, 31, 21, 0.42) 0%, rgba(18, 25, 37, 0.72) 100%)"
    };
  }

  return {
    border: `1px solid ${palette.lineTeal}`,
    background:
      "linear-gradient(180deg, rgba(16, 41, 43, 0.42) 0%, rgba(18, 25, 37, 0.72) 100%)"
  };
}

export default function ConversationThread({
  thread,
  threadState,
  threadError,
  threadNotice,
  threadNoticeTone = null,
  latestAssistantMessageId = null,
  transientPanel = null,
  finalNotice = null,
  finalNoticeTone = null
}: ConversationThreadProps) {
  const messages = thread?.messages ?? [];
  const resolvedNotice = finalNotice ?? threadNotice;
  const resolvedNoticeTone = finalNoticeTone ?? threadNoticeTone;
  const noticeStyles = getNoticeStyles(resolvedNoticeTone);

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflowX: "hidden",
        overflowY: "auto",
        scrollbarGutter: "stable",
        padding: "1rem 1.1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(11, 14, 18, 0.64) 0%, rgba(18, 25, 37, 0.52) 100%)"
      }}
    >
      <div
        style={{
          width: `min(100%, ${THREAD_COLUMN_MAX_WIDTH_PX}px)`,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: "0.8rem",
          minWidth: 0
        }}
      >
        {transientPanel}

        {resolvedNotice && (
          <div
            style={{
              padding: "0.9rem 1rem",
              borderRadius: "16px",
              ...noticeStyles,
              color: palette.silver,
              lineHeight: 1.55
            }}
          >
            {resolvedNotice}
          </div>
        )}

        {threadState === "loading" && (
          <div style={{ color: palette.silverMuted }}>Loading conversation thread…</div>
        )}

        {threadState === "error" && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "16px",
              border: "1px solid rgba(139, 78, 47, 0.32)",
              background:
                "linear-gradient(180deg, rgba(48, 23, 17, 0.44) 0%, rgba(18, 25, 37, 0.72) 100%)",
              color: palette.silverMuted,
              lineHeight: 1.55
            }}
          >
            {threadError ?? "Conversation thread could not be loaded."}
          </div>
        )}

        {threadState === "ready" && messages.length === 0 && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "16px",
              border: `1px dashed ${palette.lineBronze}`,
              background: "rgba(11, 14, 18, 0.42)",
              color: palette.silverMuted,
              lineHeight: 1.6
            }}
          >
            This conversation is empty. Begin below when you are ready.
          </div>
        )}

        {messages.map((message) => (
          <MessageBubble
            key={message.messageId}
            message={message}
            isLatestAssistantMessage={latestAssistantMessageId === message.messageId}
          />
        ))}
      </div>
    </div>
  );
}
