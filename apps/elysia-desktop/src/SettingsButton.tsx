import { forwardRef } from "react";
import { palette, shellTokens } from "./themeTokens";

type SettingsButtonProps = {
  isOpen: boolean;
  onClick: () => void;
};

const SettingsButton = forwardRef<HTMLButtonElement, SettingsButtonProps>(
  function SettingsButton({ isOpen, onClick }, ref) {
    return (
      <button
        ref={ref}
        type="button"
        aria-label="Open settings"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-controls="elysia-settings-panel"
        title="Settings"
        onClick={onClick}
        style={{
          position: "relative",
          zIndex: 1,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: "2.45rem",
          height: "2.45rem",
          padding: 0,
          borderRadius: "12px",
          border: `1px solid ${isOpen ? "rgba(126, 215, 209, 0.34)" : palette.lineSilver}`,
          background: isOpen
            ? "rgba(18, 41, 43, 0.78)"
            : shellTokens.topBarCardBackground,
          color: isOpen ? palette.teal : palette.silverMuted,
          boxShadow: isOpen ? `0 0 20px ${palette.glowTeal}` : "none",
          cursor: "pointer"
        }}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            display: "block",
            width: "1.125rem",
            height: "1.125rem",
            aspectRatio: "1 / 1",
            flex: "0 0 auto"
          }}
        >
          <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.09a2 2 0 0 1 1 1.74v.5a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2Z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
    );
  }
);

export default SettingsButton;
