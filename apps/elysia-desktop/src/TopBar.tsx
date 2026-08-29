import { useEffect, useRef, useState } from "react";
import SettingsButton from "./SettingsButton";
import SettingsPanel, { type SettingsDestination } from "./SettingsPanel";
import {
  normalizeDesktopPreferences,
  readDesktopPreferences,
  resetDesktopPreferences,
  writeDesktopPreferences,
  type DesktopPreferences
} from "./desktopPreferences";
import {
  palette,
  shellTokens
} from "./themeTokens";
import {
  activateEmergencyStop,
  fetchEmergencyState,
  resetEmergencyStop
} from "./api/emergencyClient";
import { clearMarketplaceSessionForLocalProfile } from "./api/marketplaceClient";

type TopBarProps = {
  onOpenRoom?: (room: SettingsDestination) => void;
  desktopPreferences?: DesktopPreferences;
  onDesktopPreferencesChange?: (preferences: DesktopPreferences) => void;
};

export default function TopBar({
  onOpenRoom,
  desktopPreferences,
  onDesktopPreferencesChange
}: TopBarProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [localDesktopPreferences, setLocalDesktopPreferences] =
    useState<DesktopPreferences>(readDesktopPreferences);
  const settingsContainerRef = useRef<HTMLDivElement>(null);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);
  const [stopActive, setStopActive] = useState(false);
  const [stopMessage, setStopMessage] = useState("Stop all governed work");
  const resolvedDesktopPreferences =
    desktopPreferences ?? localDesktopPreferences;

  useEffect(() => {
    if (!settingsOpen) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }

      event.preventDefault();
      setSettingsOpen(false);
      settingsButtonRef.current?.focus();
    }

    function handleMouseDown(event: MouseEvent) {
      const target = event.target;

      if (
        target instanceof Node &&
        !settingsContainerRef.current?.contains(target)
      ) {
        setSettingsOpen(false);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handleMouseDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handleMouseDown);
    };
  }, [settingsOpen]);

  useEffect(() => {
    let cancelled = false;
    async function refreshStop() {
      const result = await fetchEmergencyState();
      if (!cancelled && result.ok) {
        setStopActive(Boolean(result.payload.data?.active));
      }
    }
    void refreshStop();
    const timer = window.setInterval(() => void refreshStop(), 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  async function stopEverything(source: "button" | "keyboard") {
    setStopMessage("Stopping governed work…");
    // The browser-held Marketplace credential is a separate optional online
    // connector, never local Identity. Clear it immediately; the local API
    // stop independently closes network and worker authority.
    clearMarketplaceSessionForLocalProfile();
    const result = await activateEmergencyStop(`Operator emergency stop from Desktop ${source}`);
    setStopActive(Boolean(result.payload.data?.active) || !result.ok);
    setStopMessage(result.ok ? "Emergency posture active" : "Hard stop invoked; inspect Governance");
  }

  async function resumeAfterStop() {
    setStopMessage("Verifying safe resume authority…");
    const result = await resetEmergencyStop();
    if (result.ok) {
      setStopActive(false);
      setStopMessage("Stop all governed work");
    } else {
      setStopMessage(result.payload.errors?.[0] ?? "Owner/Admin reset required");
    }
  }

  useEffect(() => {
    function handleEmergencyShortcut(event: KeyboardEvent) {
      if (event.ctrlKey && event.shiftKey && event.key === "Escape") {
        event.preventDefault();
        void stopEverything("keyboard");
      }
    }
    window.addEventListener("keydown", handleEmergencyShortcut, { capture: true });
    return () => window.removeEventListener("keydown", handleEmergencyShortcut, { capture: true });
  }, []);

  function closeSettings() {
    setSettingsOpen(false);
    settingsButtonRef.current?.focus();
  }

  function handleDesktopPreferencesChange(preferences: DesktopPreferences) {
    const normalizedPreferences = normalizeDesktopPreferences(preferences);

    writeDesktopPreferences(normalizedPreferences);
    setLocalDesktopPreferences(normalizedPreferences);
    onDesktopPreferencesChange?.(normalizedPreferences);
  }

  function handleDesktopPreferencesReset() {
    const defaultPreferences = resetDesktopPreferences();

    setLocalDesktopPreferences(defaultPreferences);
    onDesktopPreferencesChange?.(defaultPreferences);
  }

  return (
    <header
      className="elysia-top-bar"
      style={{
        position: "relative",
        zIndex: 30,
        display: "grid",
        gridTemplateColumns: "clamp(240px, 26vw, 320px) minmax(0, 1fr) auto auto",
        alignItems: "center",
        gap: "1rem",
        padding: "0 clamp(0.85rem, 1.25vw, 1.25rem)",
        background: shellTokens.topBarBackground,
        borderBottom: `1px solid ${palette.lineBronze}`,
        boxShadow:
          "inset 0 -1px 0 rgba(199, 210, 218, 0.06), inset 0 1px 0 rgba(199, 210, 218, 0.05)"
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          background: shellTokens.topBarTraceOverlay,
          opacity: 0.5
        }}
      />

      <div style={{ position: "relative", zIndex: 1 }}>
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: palette.sandstone,
            marginBottom: "0.28rem"
          }}
        >
          Elysia Chamber
        </div>
        <div
          style={{
            fontSize: "1.25rem",
            fontWeight: 700,
            letterSpacing: "0.01em"
          }}
        >
          Local-First Chamber
        </div>
      </div>

      <div
        aria-hidden="true"
        style={{
          position: "relative",
          zIndex: 1,
          height: "1px",
          width: "100%",
          background:
            "linear-gradient(90deg, rgba(138, 106, 60, 0.16) 0%, rgba(199, 210, 218, 0.08) 50%, rgba(138, 106, 60, 0.16) 100%)"
        }}
      />

      <button
        type="button"
        onClick={() => void (stopActive ? resumeAfterStop() : stopEverything("button"))}
        aria-pressed={stopActive}
        title={stopActive ? "Owner/Admin: verify cleanup and resume" : "Emergency stop (Ctrl+Shift+Escape)"}
        style={{
          position: "relative",
          zIndex: 2,
          padding: "0.56rem 0.72rem",
          borderRadius: "11px",
          border: `1px solid ${stopActive ? "#E36B58" : palette.oxide}`,
          background: stopActive ? "rgba(132, 32, 28, 0.68)" : "rgba(82, 34, 27, 0.5)",
          color: "#F4D3CD",
          fontWeight: 800,
          cursor: "pointer"
        }}
      >
        {stopActive ? "STOP ACTIVE — Resume" : "STOP"}
        <span style={{ display: "block", fontSize: "0.58rem", fontWeight: 500 }}>{stopMessage}</span>
      </button>

      <div
        ref={settingsContainerRef}
        style={{
          position: "relative",
          zIndex: 2,
          display: "flex",
          justifyContent: "flex-end"
        }}
      >
        <SettingsButton
          ref={settingsButtonRef}
          isOpen={settingsOpen}
          onClick={() => setSettingsOpen((current) => !current)}
        />
        {settingsOpen ? (
          <SettingsPanel
            onClose={closeSettings}
            onOpenRoom={onOpenRoom}
            desktopPreferences={resolvedDesktopPreferences}
            onDesktopPreferencesChange={handleDesktopPreferencesChange}
            onDesktopPreferencesReset={handleDesktopPreferencesReset}
          />
        ) : null}
      </div>
    </header>
  );
}
