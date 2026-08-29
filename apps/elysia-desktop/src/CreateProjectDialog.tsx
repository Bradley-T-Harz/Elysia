import { useEffect, useMemo, useState } from "react";
import type { ProjectCreateRequest } from "./api/bridgeClient";

type CreateProjectDialogProps = {
  isOpen: boolean;
  startupReady: boolean;
  isSubmitting?: boolean;
  errorMessage?: string | null;
  initialName?: string;
  initialDescription?: string;
  onClose: () => void;
  onSubmit: (request: ProjectCreateRequest) => void | Promise<void>;
};

const palette = {
  obsidian: "#0B0E12",
  midnight: "#121925",
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.28)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  glowBronze: "rgba(138, 106, 60, 0.12)",
  glowTeal: "rgba(126, 215, 209, 0.14)",
  overlay: "rgba(4, 7, 11, 0.72)"
} as const;

const MAX_NAME_LENGTH = 80;
const MAX_DESCRIPTION_LENGTH = 280;

function compactText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export default function CreateProjectDialog({
  isOpen,
  startupReady,
  isSubmitting = false,
  errorMessage = null,
  initialName = "",
  initialDescription = "",
  onClose,
  onSubmit
}: CreateProjectDialogProps) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    setName(initialName);
    setDescription(initialDescription);
    setLocalError(null);
  }, [isOpen, initialDescription, initialName]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSubmitting) {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, isSubmitting, onClose]);

  const trimmedName = useMemo(() => compactText(name), [name]);
  const trimmedDescription = useMemo(() => compactText(description), [description]);

  if (!isOpen) {
    return null;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (!trimmedName) {
      setLocalError("Project name is required.");
      return;
    }

    if (trimmedName.length > MAX_NAME_LENGTH) {
      setLocalError(`Project name must stay under ${MAX_NAME_LENGTH} characters.`);
      return;
    }

    if (trimmedDescription.length > MAX_DESCRIPTION_LENGTH) {
      setLocalError(
        `Project description must stay under ${MAX_DESCRIPTION_LENGTH} characters.`
      );
      return;
    }

    setLocalError(null);

    await onSubmit({
      name: trimmedName,
      description: trimmedDescription || null
    });
  }

  const visibleError = localError || errorMessage;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-project-dialog-title"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "grid",
        placeItems: "center",
        padding: "1.25rem",
        background: palette.overlay,
        backdropFilter: "blur(6px)"
      }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: "100%",
          maxWidth: "680px",
          boxSizing: "border-box",
          minWidth: 0,
          display: "grid",
          gap: "1rem",
          padding: "1.2rem",
          borderRadius: "24px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.94) 0%, rgba(18, 25, 37, 0.98) 100%)",
          boxShadow: `0 24px 80px ${palette.overlay}`
        }}
      >
        <div style={{ display: "grid", gap: "0.45rem" }}>
          <div
            style={{
              fontSize: "0.78rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: palette.sandstone
            }}
          >
            Create project
          </div>
          <h2
            id="create-project-dialog-title"
            style={{
              margin: 0,
              fontSize: "1.5rem",
              lineHeight: 1.15,
              color: palette.silver
            }}
          >
            Open a new project chamber.
          </h2>
          <div
            style={{
              color: palette.silverMuted,
              lineHeight: 1.6,
              maxWidth: "62ch"
            }}
          >
            Keep this modest in Phase 1: create a real local project record with a
            clear name and optional description, then let later routing and project
            detail continuity build on that truth.
          </div>
        </div>

        <div
          style={{
            padding: "0.92rem 1rem",
            borderRadius: "18px",
            border: `1px dashed ${startupReady ? palette.lineTeal : palette.lineBronze}`,
            background: "rgba(11, 14, 18, 0.34)",
            color: palette.silverMuted,
            lineHeight: 1.55
          }}
        >
          {startupReady
            ? "Startup truth is ready. Project creation can proceed through the governed local path once it is wired."
            : "Startup truth is not yet ready. You can still shape the dialog, but live creation should remain explicit and carefully gated."}
        </div>

        <label style={{ display: "grid", gap: "0.45rem" }}>
          <div
            style={{
              fontSize: "0.82rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.sandstone
            }}
          >
            Project name
          </div>
          <input
            type="text"
            value={name}
            disabled={isSubmitting}
            maxLength={MAX_NAME_LENGTH}
            placeholder="Ex. EcoSyneva field intelligence"
            onChange={(event) => {
              setName(event.target.value);
              if (localError) {
                setLocalError(null);
              }
            }}
            style={{
              width: "100%",
              boxSizing: "border-box",
              minWidth: 0,
              padding: "0.82rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.42)",
              color: palette.silver,
              outline: "none",
              fontSize: "0.98rem"
            }}
          />
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "0.8rem",
              color: palette.silverMuted,
              fontSize: "0.76rem",
              lineHeight: 1.35
            }}
          >
            <span>Required. Keep it clear, stable, and human-readable.</span>
            <span>{compactText(name).length}/{MAX_NAME_LENGTH}</span>
          </div>
        </label>

        <label style={{ display: "grid", gap: "0.45rem" }}>
          <div
            style={{
              fontSize: "0.82rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.sandstone
            }}
          >
            Description
          </div>
          <textarea
            value={description}
            disabled={isSubmitting}
            maxLength={MAX_DESCRIPTION_LENGTH}
            placeholder="Optional. Add a short note about what this project chamber is for."
            onChange={(event) => {
              setDescription(event.target.value);
              if (localError) {
                setLocalError(null);
              }
            }}
            rows={5}
            style={{
              width: "100%",
              boxSizing: "border-box",
              minWidth: 0,
              resize: "vertical",
              padding: "0.82rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.42)",
              color: palette.silver,
              outline: "none",
              fontSize: "0.95rem",
              lineHeight: 1.5
            }}
          />
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "0.8rem",
              color: palette.silverMuted,
              fontSize: "0.76rem",
              lineHeight: 1.35
            }}
          >
            <span>Optional now. Notes and state summaries can deepen later.</span>
            <span>{compactText(description).length}/{MAX_DESCRIPTION_LENGTH}</span>
          </div>
        </label>

        {visibleError && (
          <div
            style={{
              padding: "0.85rem 0.95rem",
              borderRadius: "16px",
              border: `1px solid ${palette.lineBronze}`,
              background:
                "linear-gradient(180deg, rgba(42, 25, 21, 0.48) 0%, rgba(18, 25, 37, 0.74) 100%)",
              color: palette.silverMuted,
              lineHeight: 1.55
            }}
          >
            {visibleError}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "0.85rem",
            alignItems: "center",
            flexWrap: "wrap"
          }}
        >
          <div
            style={{
              color: palette.silverMuted,
              fontSize: "0.78rem",
              lineHeight: 1.45,
              maxWidth: "46ch"
            }}
          >
            This dialog only shapes the creation request. Actual bridge calls and
            routing should stay in the parent room.
          </div>

          <div
            style={{
              display: "flex",
              gap: "0.75rem",
              flexWrap: "wrap"
            }}
          >
            <button
              type="button"
              disabled={isSubmitting}
              onClick={onClose}
              style={{
                padding: "0.72rem 0.95rem",
                borderRadius: "14px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(11, 14, 18, 0.35)",
                color: palette.silver,
                cursor: isSubmitting ? "not-allowed" : "pointer",
                opacity: isSubmitting ? 0.7 : 1,
                fontSize: "0.84rem",
                fontWeight: 600
              }}
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                padding: "0.72rem 0.95rem",
                borderRadius: "14px",
                border: `1px solid ${palette.lineBronze}`,
                background:
                  "linear-gradient(180deg, rgba(43, 31, 21, 0.56) 0%, rgba(18, 25, 37, 0.72) 100%)",
                color: palette.silver,
                boxShadow: `0 0 18px ${palette.glowBronze}`,
                cursor: isSubmitting ? "progress" : "pointer",
                opacity: isSubmitting ? 0.82 : 1,
                fontSize: "0.84rem",
                fontWeight: 600,
                whiteSpace: "nowrap"
              }}
            >
              {isSubmitting ? "Creating..." : "Create project"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
