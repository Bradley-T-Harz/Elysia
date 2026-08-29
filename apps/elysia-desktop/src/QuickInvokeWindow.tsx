import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { WebviewWindow, getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import {
  newRequestId,
  sendQuickInvokeMessage
} from "./api/bridgeClient";
import { useStartupTruth } from "./hooks/useStartupTruth";

export type QuickInvokeResultStatus =
  | "ok"
  | "blocked"
  | "unavailable"
  | "degraded"
  | "error";

export type QuickInvokeTrustSummary = {
  selectedRole?: string | null;
  selectedRuntime?: string | null;
  stayedLocal?: boolean | null;
  usedFallback?: boolean | null;
  approvalNeeded?: boolean | null;
  blocked?: boolean | null;
  blockedReason?: string | null;
  degraded?: boolean | null;
  externalBoundary?: string | null;
  invocationNote?: string | null;
  requestId?: string | null;
};

export type QuickInvokeSendResult = {
  status: QuickInvokeResultStatus;
  responseText?: string | null;
  errorMessage?: string | null;
  trust?: QuickInvokeTrustSummary | null;
};

const palette = {
  bronze: "#8A6A3C",
  bronzeSoft: "rgba(138, 106, 60, 0.36)",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  oxide: "#8B4E2F",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.28)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  surface:
    "linear-gradient(180deg, rgba(18, 25, 37, 0.98) 0%, rgba(11, 14, 18, 0.98) 100%)",
  surfaceWarm:
    "linear-gradient(180deg, rgba(42, 31, 22, 0.92) 0%, rgba(18, 25, 37, 0.96) 100%)",
  surfaceSoft:
    "linear-gradient(180deg, rgba(24, 33, 48, 0.84) 0%, rgba(18, 25, 37, 0.92) 100%)",
  glowBronze: "rgba(138, 106, 60, 0.14)",
  glowTeal: "rgba(126, 215, 209, 0.12)"
} as const;

function readInitialQueryFromLocation(): string {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get("initial_query")?.trim() ?? "";
  } catch {
    return "";
  }
}

function humanizeValue(value?: string | null): string | null {
  if (!value?.trim()) {
    return null;
  }

  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b([a-z])/g, (match) => match.toUpperCase());
}

function toQuickInvokeTrustSummary(result: Awaited<ReturnType<typeof sendQuickInvokeMessage>>): QuickInvokeTrustSummary {
  const firstBlockedReason = result.truth.errors[0] ?? null;

  return {
    selectedRole: result.truth.selectedRole ?? null,
    selectedRuntime: result.truth.selectedRuntime ?? null,
    stayedLocal: result.truth.stayedLocal,
    usedFallback: result.truth.usedFallback,
    approvalNeeded: result.truth.approvalNeeded,
    blocked: result.truth.blocked,
    blockedReason: result.status === "blocked" ? firstBlockedReason : null,
    degraded: result.truth.degraded,
    externalBoundary:
      humanizeValue(result.truth.boundaryState ?? result.truth.localityState) ?? null,
    invocationNote:
      result.errorMessage ??
      result.truth.warnings[0] ??
      null,
    requestId: result.requestId ?? null
  };
}

function statusTone(status: QuickInvokeResultStatus | null): {
  label: string;
  border: string;
  background: string;
  color: string;
} {
  switch (status) {
    case "blocked":
      return {
        label: "Blocked",
        border: palette.lineBronze,
        background: "rgba(43, 31, 21, 0.58)",
        color: palette.sandstone
      };
    case "unavailable":
      return {
        label: "Unavailable",
        border: palette.lineBronze,
        background: "rgba(43, 31, 21, 0.50)",
        color: palette.sandstone
      };
    case "degraded":
      return {
        label: "Degraded",
        border: palette.lineTeal,
        background: "rgba(16, 41, 43, 0.40)",
        color: palette.teal
      };
    case "error":
      return {
        label: "Error",
        border: palette.lineBronze,
        background: "rgba(43, 31, 21, 0.56)",
        color: palette.sandstone
      };
    case "ok":
    default:
      return {
        label: "Ready",
        border: palette.lineSilver,
        background: "rgba(18, 25, 37, 0.46)",
        color: palette.silverMuted
      };
  }
}

function TruthChip({
  label,
  value,
  accent = "default"
}: {
  label: string;
  value: string;
  accent?: "default" | "warm" | "teal";
}) {
  const border =
    accent === "warm"
      ? palette.lineBronze
      : accent === "teal"
        ? palette.lineTeal
        : palette.lineSilver;

  const titleColor =
    accent === "warm"
      ? palette.sandstone
      : accent === "teal"
        ? palette.teal
        : palette.silverMuted;

  return (
    <div
      style={{
        display: "grid",
        gap: "0.16rem",
        minWidth: 0,
        padding: "0.48rem 0.58rem",
        borderRadius: "12px",
        border: `1px solid ${border}`,
        background: "rgba(18, 25, 37, 0.46)"
      }}
    >
      <div
        style={{
          fontSize: "0.68rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: titleColor
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: palette.silver,
          fontSize: "0.78rem",
          lineHeight: 1.35,
          wordBreak: "break-word"
        }}
      >
        {value}
      </div>
    </div>
  );
}

export default function QuickInvokeWindow() {
  const initialQueryFromLocation = useMemo(readInitialQueryFromLocation, []);
  const [draft, setDraft] = useState(initialQueryFromLocation);
  const [isSending, setIsSending] = useState(false);
  const [result, setResult] = useState<QuickInvokeSendResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const windowScrollRef = useRef<HTMLDivElement | null>(null);
  const responseScrollRef = useRef<HTMLDivElement | null>(null);
  const lastWindowHeightRef = useRef<number>(window.innerHeight);

  const { startupReady } = useStartupTruth();

  useEffect(() => {
    const focusTimer = window.setTimeout(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(
        textareaRef.current.value.length,
        textareaRef.current.value.length
      );
    }, 40);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        void handleCloseWindow();
      }
    };

    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  useEffect(() => {
    if (!result && !errorMessage) {
      return;
    }

    const scrollTimer = window.setTimeout(() => {
      responseScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    }, 0);

    return () => {
      window.clearTimeout(scrollTimer);
    };
  }, [result?.trust?.requestId, result?.responseText, result?.status, errorMessage]);

  useEffect(() => {
    const handleResize = () => {
      const previousHeight = lastWindowHeightRef.current;
      const currentHeight = window.innerHeight;
      const grewTaller = currentHeight > previousHeight;

      lastWindowHeightRef.current = currentHeight;

      if (!grewTaller) {
        return;
      }

      responseScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
      windowScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  const canSubmit = startupReady && !isSending && draft.trim().length > 0;

  const tone = useMemo(
    () => statusTone(result?.status ?? (errorMessage ? "error" : null)),
    [errorMessage, result?.status]
  );

  const trustRows = useMemo(() => {
    const trust = result?.trust;
    if (!trust) {
      return [];
    }

    const rows: Array<{
      key: string;
      label: string;
      value: string;
      accent?: "default" | "warm" | "teal";
    }> = [];

    const selectedRole = humanizeValue(trust.selectedRole);
    if (selectedRole) {
      rows.push({
        key: "selected_role",
        label: "Role",
        value: selectedRole
      });
    }

    const selectedRuntime = humanizeValue(trust.selectedRuntime);
    if (selectedRuntime) {
      rows.push({
        key: "selected_runtime",
        label: "Runtime",
        value: selectedRuntime
      });
    }

    if (typeof trust.stayedLocal === "boolean") {
      rows.push({
        key: "stayed_local",
        label: "Locality",
        value: trust.stayedLocal ? "Stayed local" : "Crossed boundary",
        accent: trust.stayedLocal ? "teal" : "warm"
      });
    }

    if (typeof trust.usedFallback === "boolean") {
      rows.push({
        key: "used_fallback",
        label: "Fallback",
        value: trust.usedFallback ? "Used fallback" : "Primary path",
        accent: trust.usedFallback ? "warm" : "default"
      });
    }

    if (typeof trust.approvalNeeded === "boolean") {
      rows.push({
        key: "approval_needed",
        label: "Approval",
        value: trust.approvalNeeded ? "Approval needed" : "Not needed",
        accent: trust.approvalNeeded ? "warm" : "default"
      });
    }

    if (typeof trust.blocked === "boolean") {
      rows.push({
        key: "blocked",
        label: "Boundary",
        value: trust.blocked ? "Blocked" : "Not blocked",
        accent: trust.blocked ? "warm" : "default"
      });
    }

    const externalBoundary = humanizeValue(trust.externalBoundary);
    if (externalBoundary) {
      rows.push({
        key: "external_boundary",
        label: "Boundary",
        value: externalBoundary,
        accent: "warm"
      });
    }

    if (typeof trust.degraded === "boolean" && trust.degraded) {
      rows.push({
        key: "degraded",
        label: "Runtime",
        value: "Degraded",
        accent: "teal"
      });
    }

    const blockedReason = trust.blockedReason?.trim();
    if (blockedReason) {
      rows.push({
        key: "blocked_reason",
        label: "Reason",
        value: blockedReason,
        accent: "warm"
      });
    }

    return rows;
  }, [result?.trust]);

  const helperCopy = useMemo(() => {
    if (!startupReady) {
      return "Quick Invoke is mounted, but startup truth is not ready yet.";
    }

    if (isSending) {
      return "Sending through the same governed chamber path.";
    }

    if (errorMessage) {
      return errorMessage;
    }

    if (result?.status === "blocked") {
      return (
        result.errorMessage ??
        result.trust?.blockedReason ??
        "The request was blocked by current boundary law."
      );
    }

    if (result?.status === "unavailable") {
      return result.errorMessage ?? "Quick Invoke is temporarily unavailable.";
    }

    if (result?.status === "degraded") {
      return (
        result.errorMessage ??
        result.trust?.invocationNote ??
        "The response arrived through a degraded path."
      );
    }

    if (result?.status === "error") {
      return result.errorMessage ?? "Quick Invoke encountered an error.";
    }

    if (result?.trust?.invocationNote?.trim()) {
      return result.trust.invocationNote.trim();
    }

    return "One fast ask. Same governed body path. No bypass.";
  }, [errorMessage, isSending, result, startupReady]);

  async function handleSubmit(event?: FormEvent) {
    event?.preventDefault();

    const text = draft.trim();
    if (!text || isSending || !startupReady) {
      return;
    }

    setIsSending(true);
    setErrorMessage(null);

    try {
      const response = await sendQuickInvokeMessage({
        message: text,
        request_id: newRequestId("qinv"),
        ui_surface: "quick_invoke"
      });

      setResult({
        status: response.status,
        responseText: response.responseText ?? null,
        errorMessage: response.errorMessage ?? null,
        trust: toQuickInvokeTrustSummary(response)
      });

      if (response.status === "error" && response.errorMessage?.trim()) {
        setErrorMessage(response.errorMessage.trim());
      }
    } catch (error) {
      setResult({
        status: "error",
        errorMessage:
          error instanceof Error
            ? error.message
            : "Quick Invoke failed unexpectedly."
      });
      setErrorMessage(
        error instanceof Error ? error.message : "Quick Invoke failed unexpectedly."
      );
    } finally {
      setIsSending(false);
    }
  }

  async function handleCloseWindow() {
    try {
      await getCurrentWebviewWindow().close();
    } catch (error) {
      console.error("[quickInvoke] failed to close child window", error);
    }
  }

  async function handleOpenFullApp() {
    try {
      const mainWindow = await WebviewWindow.getByLabel("main");
      if (mainWindow) {
        await mainWindow.emit("quick-invoke-open-full-app", {
          draft,
          responseText: result?.responseText ?? null,
          requestId: result?.trust?.requestId ?? null
        });
        await mainWindow.setFocus();
      }

      await handleCloseWindow();
    } catch (error) {
      console.error("[quickInvoke] failed to focus main window", error);
    }
  }

  return (
    <div
      ref={windowScrollRef}
      aria-label="Quick Invoke window"
      style={{
        height: "100vh",
        boxSizing: "border-box",
        padding: "0.6rem",
        overflow: "auto",
        background:
          "radial-gradient(circle at 18% 12%, rgba(126, 215, 209, 0.08), transparent 18%), radial-gradient(circle at 84% 9%, rgba(138, 106, 60, 0.08), transparent 20%), linear-gradient(180deg, #111726 0%, #0B0E12 100%)",
        color: palette.silver,
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
      }}
    >
      <div
        style={{
          width: "100%",
          minHeight: "100%",
          display: "grid",
          gridTemplateRows: "auto auto auto minmax(0, 1fr)",
          gap: "0.72rem",
          padding: "0.82rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineSilver}`,
          background: palette.surface,
          boxShadow:
            "0 22px 52px rgba(0,0,0,0.30), 0 0 26px rgba(126, 215, 209, 0.08)",
          boxSizing: "border-box",
          overflow: "hidden"
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "0.8rem"
          }}
        >
          <div style={{ display: "grid", gap: "0.28rem", minWidth: 0 }}>
            <div
              style={{
                fontSize: "0.74rem",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: palette.sandstone
              }}
            >
              Quick Invoke
            </div>
            <div
              style={{
                color: palette.silver,
                fontSize: "1.18rem",
                fontWeight: 600,
                lineHeight: 1.15
              }}
            >
              Compact entrance, not bypass.
            </div>
            <div
              style={{
                color: palette.silverMuted,
                fontSize: "0.88rem",
                lineHeight: 1.5,
                maxWidth: "56ch"
              }}
            >
              Send one fast request through the same governed chamber path, then
              return to the full app when the work deepens.
            </div>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.8rem",
            padding: "0.55rem 0.65rem",
            borderRadius: "14px",
            border: `1px solid ${tone.border}`,
            background: tone.background
          }}
        >
          <div
            style={{
              color: tone.color,
              fontSize: "0.84rem",
              lineHeight: 1.45
            }}
          >
            {helperCopy}
          </div>

          <div
            style={{
              flex: "0 0 auto",
              padding: "0.26rem 0.58rem",
              borderRadius: "999px",
              border: `1px solid ${tone.border}`,
              color: tone.color,
              fontSize: "0.72rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase"
            }}
          >
            {isSending ? "Sending" : tone.label}
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          style={{
            display: "grid",
            gap: "0.72rem"
          }}
        >
          <div
            style={{
              display: "grid",
              gap: "0.36rem"
            }}
          >
            <label
              htmlFor="quick-invoke-input"
              style={{
                color: palette.silverMuted,
                fontSize: "0.76rem",
                letterSpacing: "0.06em",
                textTransform: "uppercase"
              }}
            >
              Fast ask
            </label>

            <textarea
              id="quick-invoke-input"
              ref={textareaRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask Elysia one fast question..."
              rows={3}
              disabled={!startupReady || isSending}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  void handleSubmit();
                }
              }}
              style={{
                width: "100%",
                resize: "vertical",
                minHeight: "5.6rem",
                padding: "0.88rem 0.95rem",
                borderRadius: "16px",
                border: `1px solid ${palette.lineSilver}`,
                background: palette.surfaceSoft,
                color: palette.silver,
                fontSize: "0.95rem",
                lineHeight: 1.55,
                boxSizing: "border-box",
                outline: "none"
              }}
            />
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.8rem",
              flexWrap: "wrap"
            }}
          >
            <div
              style={{
                color: palette.silverMuted,
                fontSize: "0.8rem",
                lineHeight: 1.45
              }}
            >
              Cmd/Ctrl + Enter sends. Escape closes.
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.55rem",
                flexWrap: "wrap",
                justifyContent: "flex-end"
              }}
            >
              <button
                type="button"
                onClick={() => void handleOpenFullApp()}
                style={{
                  padding: "0.62rem 0.88rem",
                  borderRadius: "14px",
                  border: `1px solid ${palette.lineSilver}`,
                  background: "rgba(18, 25, 37, 0.56)",
                  color: palette.silver,
                  cursor: "pointer",
                  fontSize: "0.84rem",
                  fontWeight: 600
                }}
              >
                Open full app
              </button>

              <button
                type="submit"
                disabled={!canSubmit}
                style={{
                  padding: "0.62rem 0.92rem",
                  borderRadius: "14px",
                  border: `1px solid ${palette.lineBronze}`,
                  background: palette.surfaceWarm,
                  color: palette.silver,
                  boxShadow: `0 0 16px ${palette.glowBronze}`,
                  cursor: canSubmit ? "pointer" : "not-allowed",
                  opacity: canSubmit ? 1 : 0.68,
                  fontSize: "0.84rem",
                  fontWeight: 600
                }}
              >
                {isSending ? "Sending..." : "Send"}
              </button>
            </div>
          </div>
        </form>

        {(result?.responseText?.trim() || trustRows.length > 0 || result?.status) && (
          <div
            ref={responseScrollRef}
            style={{
              display: "grid",
              gap: "0.68rem",
              padding: "0.82rem",
              borderRadius: "18px",
              border: `1px solid ${palette.lineSilver}`,
              background:
                "linear-gradient(180deg, rgba(24, 33, 48, 0.62) 0%, rgba(18, 25, 37, 0.82) 100%)",
              overflow: "auto",
              minHeight: 0,
              alignSelf: "stretch"
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "0.6rem"
              }}
            >
              <div
                style={{
                  fontSize: "0.74rem",
                  letterSpacing: "0.10em",
                  textTransform: "uppercase",
                  color: palette.sandstone
                }}
              >
                Response
              </div>

              {result?.trust?.requestId?.trim() && (
                <div
                  style={{
                    color: palette.silverMuted,
                    fontSize: "0.74rem",
                    lineHeight: 1.3
                  }}
                >
                  Request {result.trust.requestId.trim()}
                </div>
              )}
            </div>

            {result?.responseText?.trim() ? (
              <div
                style={{
                  color: palette.silver,
                  fontSize: "0.92rem",
                  lineHeight: 1.62,
                  whiteSpace: "pre-wrap"
                }}
              >
                {result.responseText.trim()}
              </div>
            ) : (
              <div
                style={{
                  color: palette.silverMuted,
                  fontSize: "0.88rem",
                  lineHeight: 1.5
                }}
              >
                No response text surfaced yet.
              </div>
            )}

            {trustRows.length > 0 && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(132px, 1fr))",
                  gap: "0.48rem"
                }}
              >
                {trustRows.map((row) => (
                  <TruthChip
                    key={row.key}
                    label={row.label}
                    value={row.value}
                    accent={row.accent}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
