import type { KeyboardEvent } from "react";

export type ComposerAttachedFile = {
  fileId: string;
  displayName: string;
  fileKind?: string | null;
  processingState?: string | null;
  memoryPosture?: string | null;
  usableAsContext?: boolean | null;
  ready?: boolean | null;
  blocked?: boolean | null;
  errors?: string[];
};

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  sending?: boolean;
  disabledReason?: string | null;
  sendError?: string | null;
  statusText?: string | null;
  placeholder?: string;
  rows?: number;
  filePathValue?: string;
  onFilePathChange?: (value: string) => void;
  onAttachFilePath?: () => void;
  onBrowseForFile?: () => void;
  attachingFile?: boolean;
  browsingFile?: boolean;
  fileAttachDisabled?: boolean;
  fileBrowseDisabled?: boolean;
  fileAttachError?: string | null;
  attachedFiles?: ComposerAttachedFile[];
  onRemoveAttachedFile?: (fileId: string) => void;
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

function hasSendableText(value: string): boolean {
  return value.trim().length > 0;
}

function attachedFileLaneLabel(attachedFile: ComposerAttachedFile): string {
  const fileKind = String(attachedFile.fileKind ?? "").trim().toLowerCase();
  const processingState = String(attachedFile.processingState ?? "").trim().toLowerCase();

  if (attachedFile.blocked || processingState === "blocked") {
    return "blocked";
  }

  if (fileKind === "csv" || fileKind === "xlsx") {
    return "data summary input";
  }

  if (fileKind === "text" || fileKind === "markdown") {
    return "text context";
  }

  return "attached";
}

export default function Composer({
  value,
  onChange,
  onSend,
  disabled = false,
  sending = false,
  disabledReason = null,
  sendError = null,
  statusText = null,
  placeholder = "Ask Elysia something local and real.",
  rows = 5,
  filePathValue = "",
  onFilePathChange,
  onAttachFilePath,
  onBrowseForFile,
  attachingFile = false,
  browsingFile = false,
  fileAttachDisabled = false,
  fileBrowseDisabled = false,
  fileAttachError = null,
  attachedFiles = [],
  onRemoveAttachedFile
}: ComposerProps) {
  const sendable = hasSendableText(value);
  const textareaDisabled = sending;
  const canSend = !disabled && !sending && sendable;
  const noticeText = sendError ?? disabledReason ?? null;
  const attachedFileItems = attachedFiles ?? [];
  const filePathText = filePathValue.trim();
  const fileInputDisabled =
    sending || attachingFile || browsingFile || fileAttachDisabled || !onFilePathChange;
  const browseButtonDisabled =
    sending || attachingFile || browsingFile || fileBrowseDisabled || !onBrowseForFile;
  const canAttachFile =
    !sending &&
    !attachingFile &&
    !browsingFile &&
    !fileAttachDisabled &&
    Boolean(onAttachFilePath) &&
    filePathText.length > 0;

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }

    if (!canSend) {
      return;
    }

    event.preventDefault();
    onSend();
  }

  function handleFilePathKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") {
      return;
    }

    if (!canAttachFile) {
      return;
    }

    event.preventDefault();
    onAttachFilePath?.();
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(155px, auto) minmax(0, 1fr) auto",
        gap: "0.55rem",
        width: "100%",
        minWidth: 0,
        overflow: "hidden",
        boxSizing: "border-box",
        padding: "0.75rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.68) 0%, rgba(18, 25, 37, 0.74) 100%)"
      }}
    >
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={rows}
        disabled={textareaDisabled}
        style={{
          gridColumn: "1 / -1",
          display: "block",
          width: "100%",
          maxWidth: "100%",
          minWidth: 0,
          boxSizing: "border-box",
          resize: "vertical",
          padding: "0.75rem 0.85rem",
          borderRadius: "16px",
          border: `1px solid ${palette.lineSilver}`,
          background: "rgba(11, 14, 18, 0.58)",
          color: palette.silver,
          lineHeight: 1.55,
          opacity: textareaDisabled ? 0.82 : 1
        }}
      />

      <details
        className="elysia-composer-file-tools"
        style={{
          gridColumn: "1",
          display: "grid",
          gap: "0.45rem",
          padding: "0.6rem 0.65rem",
          borderRadius: "16px",
          border: `1px dashed ${palette.lineBronze}`,
          background: "rgba(11, 14, 18, 0.34)"
        }}
      >
        <summary
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "0.75rem",
            alignItems: "center",
            minHeight: "1.75rem",
            color: palette.sandstone,
            cursor: "pointer",
            fontSize: "0.78rem",
            fontWeight: 700,
            letterSpacing: "0.06em",
            textTransform: "uppercase"
          }}
        >
          <span>Attach a local file</span>
          <span
            style={{
              color: fileAttachError ? palette.sandstone : palette.silverMuted,
              fontSize: "0.74rem",
              fontWeight: 600,
              letterSpacing: "normal",
              textTransform: "none"
            }}
          >
            {fileAttachError
              ? "Needs attention"
              : attachedFileItems.length > 0
                ? `${attachedFileItems.length} attached`
                : "Optional"}
          </span>
        </summary>

        <div
          style={{
            display: "grid",
            gap: "0.25rem"
          }}
        >
          <div
            style={{
              color: palette.sandstone,
              fontSize: "0.76rem",
              letterSpacing: "0.09em",
              textTransform: "uppercase"
            }}
          >
            Attach local TXT/Markdown/CSV/XLSX path
          </div>
          <div
            style={{
              color: palette.silverMuted,
              fontSize: "0.82rem",
              lineHeight: 1.45
            }}
          >
            TXT/Markdown can be used as bounded text context. CSV/XLSX can be used
            for bounded local data summary. Attached files are not memory.
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: "0.55rem",
            flexWrap: "wrap",
            alignItems: "center",
            minWidth: 0
          }}
        >
          <input
            type="text"
            value={filePathValue}
            onChange={(event) => onFilePathChange?.(event.target.value)}
            onKeyDown={handleFilePathKeyDown}
            disabled={fileInputDisabled}
            placeholder="notes.md, data.csv, workbook.xlsx, or another user-selected file"
            style={{
              flex: "1 1 320px",
              minWidth: 0,
              boxSizing: "border-box",
              padding: "0.68rem 0.8rem",
              borderRadius: "13px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.52)",
              color: palette.silver,
              opacity: fileInputDisabled ? 0.72 : 1
            }}
          />

          <button
            type="button"
            onClick={onBrowseForFile}
            disabled={browseButtonDisabled}
            style={{
              padding: "0.68rem 0.9rem",
              borderRadius: "13px",
              border: `1px solid ${browseButtonDisabled ? palette.lineBronze : palette.lineSilver}`,
              background: browseButtonDisabled
                ? "linear-gradient(180deg, rgba(43, 31, 21, 0.50) 0%, rgba(18, 25, 37, 0.72) 100%)"
                : "linear-gradient(180deg, rgba(18, 25, 37, 0.80) 0%, rgba(11, 14, 18, 0.72) 100%)",
              color: browseButtonDisabled ? palette.silverMuted : palette.silver,
              cursor: browseButtonDisabled ? "default" : "pointer",
              opacity: browseButtonDisabled ? 0.72 : 1,
              flexShrink: 0
            }}
          >
            {browsingFile ? "Browsing…" : "Browse…"}
          </button>

          <button
            type="button"
            onClick={onAttachFilePath}
            disabled={!canAttachFile}
            style={{
              padding: "0.68rem 0.9rem",
              borderRadius: "13px",
              border: `1px solid ${canAttachFile ? palette.lineTeal : palette.lineBronze}`,
              background: canAttachFile
                ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.80) 100%)"
                : "linear-gradient(180deg, rgba(43, 31, 21, 0.50) 0%, rgba(18, 25, 37, 0.72) 100%)",
              color: canAttachFile ? palette.teal : palette.silverMuted,
              cursor: canAttachFile ? "pointer" : "default",
              opacity: canAttachFile ? 1 : 0.72,
              flexShrink: 0
            }}
          >
            {attachingFile ? "Attaching…" : "Attach"}
          </button>
        </div>

        {fileAttachError && (
          <div
            style={{
              padding: "0.65rem 0.75rem",
              borderRadius: "13px",
              border: `1px solid ${palette.lineBronze}`,
              background: "rgba(43, 31, 21, 0.32)",
              color: palette.silverMuted,
              lineHeight: 1.45
            }}
          >
            {fileAttachError}
          </div>
        )}

        {attachedFileItems.length > 0 && (
          <div
            style={{
              display: "flex",
              gap: "0.5rem",
              flexWrap: "wrap"
            }}
          >
            {attachedFileItems.map((attachedFile) => {
              const stateLabel =
                attachedFile.processingState ??
                (attachedFile.ready
                  ? "ready"
                  : attachedFile.blocked
                    ? "blocked"
                    : "attached");
              const memoryLabel = attachedFile.memoryPosture ?? "not_memory";
              const laneLabel = attachedFileLaneLabel(attachedFile);
              const borderColor =
                attachedFile.blocked || stateLabel === "blocked"
                  ? palette.lineBronze
                  : attachedFile.ready || stateLabel === "ready"
                    ? palette.lineTeal
                    : palette.lineSilver;

              return (
                <div
                  key={attachedFile.fileId}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.45rem",
                    maxWidth: "100%",
                    padding: "0.48rem 0.62rem",
                    borderRadius: "999px",
                    border: `1px solid ${borderColor}`,
                    background: "rgba(18, 25, 37, 0.68)",
                    color: palette.silverMuted,
                    fontSize: "0.78rem",
                    minWidth: 0
                  }}
                  title={attachedFile.errors?.join("\n") || attachedFile.fileId}
                >
                  <span
                    style={{
                      color: palette.silver,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      minWidth: 0
                    }}
                  >
                    {attachedFile.displayName}
                  </span>
                  <span>{stateLabel}</span>
                  <span>{laneLabel}</span>
                  <span>{memoryLabel}</span>

                  {onRemoveAttachedFile && (
                    <button
                      type="button"
                      onClick={() => onRemoveAttachedFile(attachedFile.fileId)}
                      style={{
                        border: "none",
                        background: "transparent",
                        color: palette.silverMuted,
                        cursor: "pointer",
                        padding: "0 0.15rem",
                        fontSize: "0.9rem",
                        lineHeight: 1
                      }}
                      aria-label={`Remove ${attachedFile.displayName}`}
                    >
                      ×
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </details>

      {noticeText && (
        <div
          style={{
            gridColumn: "1 / -1",
            padding: "0.8rem 0.9rem",
            borderRadius: "14px",
            border: `1px solid ${palette.lineBronze}`,
            background: "rgba(11, 14, 18, 0.42)",
            color: palette.silverMuted,
            lineHeight: 1.55
          }}
        >
          {noticeText}
        </div>
      )}

      <div
        className="elysia-composer-footer"
        style={{
          gridColumn: "2 / -1",
          display: "flex",
          justifyContent: "space-between",
          gap: "0.75rem",
          alignItems: "center",
          flexWrap: "wrap",
          minWidth: 0
        }}
      >
        <div
          style={{
            color: palette.silverMuted,
            fontSize: "0.82rem",
            flex: "1 1 150px",
            minWidth: 0
          }}
        >
          {statusText ??
            (sending
              ? "A governed request is moving through the local bridge."
              : "Compose a local request and send when ready.")}
        </div>

        <button
          type="button"
          onClick={onSend}
          disabled={!canSend}
          style={{
            padding: "0.7rem 1rem",
            borderRadius: "14px",
            border: `1px solid ${!canSend ? palette.lineBronze : palette.lineTeal}`,
            background: !canSend
              ? "linear-gradient(180deg, rgba(43, 31, 21, 0.50) 0%, rgba(18, 25, 37, 0.72) 100%)"
              : "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.80) 100%)",
            color: !canSend ? palette.silverMuted : palette.teal,
            cursor: !canSend ? "default" : "pointer",
            opacity: !canSend ? 0.72 : 1,
            flexShrink: 0
          }}
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}
