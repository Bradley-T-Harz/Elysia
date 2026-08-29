import { useEffect, useState } from "react";

type RenameConversationDialogProps = {
  open: boolean;
  currentTitle: string;
  busy?: boolean;
  onClose: () => void;
  onSubmit: (nextTitle: string) => void;
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

export default function RenameConversationDialog({
  open,
  currentTitle,
  busy = false,
  onClose,
  onSubmit
}: RenameConversationDialogProps) {
  const [draftTitle, setDraftTitle] = useState(currentTitle);

  useEffect(() => {
    if (open) {
      setDraftTitle(currentTitle);
    }
  }, [open, currentTitle]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) {
        onClose();
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [busy, onClose, open]);

  if (!open) {
    return null;
  }

  const trimmedTitle = draftTitle.trim();
  const canSubmit = !busy && trimmedTitle.length > 0 && trimmedTitle !== currentTitle.trim();

  function handleSubmit() {
    if (!canSubmit) {
      return;
    }

    onSubmit(trimmedTitle);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Rename conversation"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 120,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.25rem",
        background: "rgba(5, 8, 12, 0.58)",
        backdropFilter: "blur(4px)"
      }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) {
          onClose();
        }
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "30rem",
          display: "grid",
          gap: "1rem",
          padding: "1.15rem",
          borderRadius: "22px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.96) 0%, rgba(18, 25, 37, 0.98) 100%)",
          boxShadow: "0 18px 42px rgba(0,0,0,0.32)"
        }}
      >
        <div>
          <div
            style={{
              fontSize: "0.76rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.35rem"
            }}
          >
            Rename
          </div>
          <h2
            style={{
              margin: 0,
              fontSize: "1.35rem",
              lineHeight: 1.15,
              color: palette.silver
            }}
          >
            Rename conversation
          </h2>
          <div
            style={{
              marginTop: "0.45rem",
              color: palette.silverMuted,
              lineHeight: 1.55
            }}
          >
            Give this conversation a clearer local title.
          </div>
        </div>

        <div style={{ display: "grid", gap: "0.5rem" }}>
          <label
            htmlFor="rename-conversation-input"
            style={{
              fontSize: "0.82rem",
              color: palette.silverMuted
            }}
          >
            Title
          </label>

          <input
            id="rename-conversation-input"
            type="text"
            value={draftTitle}
            onChange={(event) => setDraftTitle(event.target.value)}
            disabled={busy}
            autoFocus
            style={{
              width: "100%",
              padding: "0.85rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.58)",
              color: palette.silver,
              boxSizing: "border-box"
            }}
          />
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.7rem",
            flexWrap: "wrap"
          }}
        >
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            style={{
              padding: "0.7rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineBronze}`,
              background:
                "linear-gradient(180deg, rgba(43, 31, 21, 0.46) 0%, rgba(18, 25, 37, 0.70) 100%)",
              color: palette.silverMuted,
              cursor: busy ? "default" : "pointer",
              opacity: busy ? 0.72 : 1
            }}
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              padding: "0.7rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${canSubmit ? palette.lineTeal : palette.lineBronze}`,
              background: canSubmit
                ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.80) 100%)"
                : "linear-gradient(180deg, rgba(43, 31, 21, 0.46) 0%, rgba(18, 25, 37, 0.70) 100%)",
              color: canSubmit ? palette.teal : palette.silverMuted,
              cursor: canSubmit ? "pointer" : "default",
              opacity: canSubmit ? 1 : 0.72
            }}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
