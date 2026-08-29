import type { CSSProperties, ReactNode } from "react";

export type QuickInvokeLauncherVariant = "compact" | "icon" | "inline";

export type QuickInvokeLauncherProps = {
  onOpenQuickInvoke?: () => void;
  disabled?: boolean;
  inertButClickable?: boolean;
  ariaLabel?: string;
  title?: string;
  variant?: QuickInvokeLauncherVariant;
  leadingIcon?: ReactNode;
  label?: string;
  caption?: string | null;
  children?: ReactNode;
  style?: CSSProperties;
};

const palette = {
  bronze: "#8A6A3C",
  bronzeSoft: "rgba(138, 106, 60, 0.38)",
  sandstone: "#B8A27B",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.28)",
  glowBronze: "rgba(138, 106, 60, 0.14)",
  surface:
    "linear-gradient(180deg, rgba(42, 31, 22, 0.94) 0%, rgba(18, 25, 37, 0.96) 100%)",
  surfaceSoft:
    "linear-gradient(180deg, rgba(24, 33, 48, 0.84) 0%, rgba(18, 25, 37, 0.92) 100%)"
} as const;

export function useQuickInvokeLauncher({
  onOpenQuickInvoke,
  disabled = false,
  inertButClickable = false,
  title
}: {
  onOpenQuickInvoke?: () => void;
  disabled?: boolean;
  inertButClickable?: boolean;
  title?: string;
}) {
  const canInvoke = Boolean(onOpenQuickInvoke) && !disabled;

  function handleActivate() {
    if (disabled) {
      return;
    }

    if (onOpenQuickInvoke) {
      onOpenQuickInvoke();
      return;
    }

    if (inertButClickable) {
      return;
    }
  }

  return {
    canInvoke,
    handleActivate,
    resolvedTitle:
      title ??
      (canInvoke
        ? "Open Quick Invoke"
        : inertButClickable
          ? "Quick Invoke"
          : "Quick Invoke not wired yet"),
    cursor:
      disabled ? "not-allowed" : canInvoke || inertButClickable ? "pointer" : "default"
  };
}

function iconButtonStyle(cursor: string): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    border: "none",
    background: "transparent",
    boxShadow:
      "0 0 0 1px rgba(138, 106, 60, 0.16), 0 4px 14px rgba(0,0,0,0.18)",
    overflow: "hidden",
    flex: "0 0 auto",
    cursor
  };
}

function compactButtonStyle(cursor: string): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.68rem",
    minWidth: 0,
    padding: "0.62rem 0.74rem",
    borderRadius: "14px",
    border: `1px solid ${palette.lineBronze}`,
    background: palette.surface,
    color: palette.silver,
    boxShadow: `0 0 14px ${palette.glowBronze}`,
    cursor
  };
}

function inlineButtonStyle(cursor: string): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.46rem",
    padding: "0.38rem 0.52rem",
    borderRadius: "12px",
    border: `1px solid ${palette.lineSilver}`,
    background: palette.surfaceSoft,
    color: palette.silver,
    cursor
  };
}

export default function QuickInvokeLauncher({
  onOpenQuickInvoke,
  disabled = false,
  inertButClickable = false,
  ariaLabel = "Quick Invoke",
  title,
  variant = "compact",
  leadingIcon,
  label = "Quick Invoke",
  caption = "Compact entrance above chamber.",
  children,
  style
}: QuickInvokeLauncherProps) {
  const { handleActivate, resolvedTitle, cursor } = useQuickInvokeLauncher({
    onOpenQuickInvoke,
    disabled,
    inertButClickable,
    title
  });

  if (variant === "icon") {
    return (
      <button
        type="button"
        aria-label={ariaLabel}
        title={resolvedTitle}
        onClick={handleActivate}
        disabled={disabled}
        style={{
          ...iconButtonStyle(cursor),
          ...style
        }}
      >
        {children ?? leadingIcon}
      </button>
    );
  }

  if (variant === "inline") {
    return (
      <button
        type="button"
        aria-label={ariaLabel}
        title={resolvedTitle}
        onClick={handleActivate}
        disabled={disabled}
        style={{
          ...inlineButtonStyle(cursor),
          ...style
        }}
      >
        {leadingIcon ? (
          <span
            aria-hidden="true"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              flex: "0 0 auto"
            }}
          >
            {leadingIcon}
          </span>
        ) : null}

        {children ?? (
          <span
            style={{
              color: palette.silver,
              fontSize: "0.82rem",
              lineHeight: 1.2
            }}
          >
            {label}
          </span>
        )}
      </button>
    );
  }

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      title={resolvedTitle}
      onClick={handleActivate}
      disabled={disabled}
      style={{
        ...compactButtonStyle(cursor),
        ...style
      }}
    >
      {leadingIcon ? (
        <span
          aria-hidden="true"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            flex: "0 0 auto"
          }}
        >
          {leadingIcon}
        </span>
      ) : null}

      {children ?? (
        <span
          style={{
            display: "grid",
            gap: "0.12rem",
            minWidth: 0,
            textAlign: "left"
          }}
        >
          <span
            style={{
              fontSize: "0.78rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.sandstone
            }}
          >
            {label}
          </span>

          {caption ? (
            <span
              style={{
                color: palette.silverMuted,
                fontSize: "0.76rem",
                lineHeight: 1.35
              }}
            >
              {caption}
            </span>
          ) : null}
        </span>
      )}
    </button>
  );
}
