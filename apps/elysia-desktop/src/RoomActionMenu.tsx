import {
  useEffect,
  useRef,
  useState,
  type RefObject
} from "react";
import { createPortal } from "react-dom";

export type RoomActionMenuItem =
  | {
      kind?: "item";
      key: string;
      label: string;
      detail?: string;
      stateLabel?: string;
      onSelect?: () => void;
      submenu?: RoomActionMenuItem[];
      disabled?: boolean;
    }
  | {
      kind: "divider";
      key: string;
    };

type RoomActionMenuProps = {
  open: boolean;
  onClose: () => void;
  items: RoomActionMenuItem[];
  anchorRef: RefObject<HTMLElement | null>;
  align?: "start" | "end";
  minWidth?: number;
};

type MenuPlacement = {
  left: number;
  top: number;
};

type SubmenuState = {
  key: string;
  items: RoomActionMenuItem[];
  position: MenuPlacement;
};

const palette = {
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)"
} as const;

function isDivider(
  item: RoomActionMenuItem
): item is Extract<RoomActionMenuItem, { kind: "divider" }> {
  return item.kind === "divider";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function estimateMenuHeight(items: RoomActionMenuItem[]): number {
  return Math.min(
    420,
    items.reduce((total, item) => total + (isDivider(item) ? 10 : 46), 18)
  );
}

export default function RoomActionMenu({
  open,
  onClose,
  items,
  anchorRef,
  align = "end",
  minWidth = 220
}: RoomActionMenuProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [anchorPosition, setAnchorPosition] = useState<MenuPlacement | null>(null);
  const [submenuState, setSubmenuState] = useState<SubmenuState | null>(null);

  useEffect(() => {
    if (!open) {
      setAnchorPosition(null);
      setSubmenuState(null);
      return;
    }

    function updateAnchorPosition() {
      const anchor = anchorRef.current;
      if (!anchor) {
        setAnchorPosition(null);
        return;
      }

      const rect = anchor.getBoundingClientRect();
      const estimatedWidth = minWidth + 16;
      const estimatedHeight = estimateMenuHeight(items);

      const preferredTop = rect.bottom + 8;
      const flippedTop = rect.top - estimatedHeight - 8;
      const top =
        preferredTop + estimatedHeight > window.innerHeight - 12
          ? Math.max(12, flippedTop)
          : preferredTop;

      const preferredLeft =
        align === "end" ? rect.right - estimatedWidth : rect.left;

      const left = clamp(
        preferredLeft,
        12,
        Math.max(12, window.innerWidth - estimatedWidth - 12)
      );

      setAnchorPosition({ left, top });
      setSubmenuState(null);
    }

    function handlePointerDown(event: MouseEvent) {
      const root = rootRef.current;
      if (!root) {
        return;
      }

      if (!root.contains(event.target as Node)) {
        onClose();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    updateAnchorPosition();

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", updateAnchorPosition);
    window.addEventListener("scroll", updateAnchorPosition, true);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", updateAnchorPosition);
      window.removeEventListener("scroll", updateAnchorPosition, true);
    };
  }, [align, anchorRef, items, minWidth, onClose, open]);

  if (!open || !anchorPosition) {
    return null;
  }

  function buildSubmenuPosition(
    element: HTMLElement,
    submenuItems: RoomActionMenuItem[]
  ): MenuPlacement {
    const rect = element.getBoundingClientRect();
    const estimatedWidth = minWidth + 16;
    const estimatedHeight = estimateMenuHeight(submenuItems);
    const gap = 8;

    const openRight = rect.right + gap + estimatedWidth <= window.innerWidth - 12;

    const left = openRight
      ? rect.right + gap
      : Math.max(12, rect.left - estimatedWidth - gap);

    const top = clamp(
      rect.top - 8,
      12,
      Math.max(12, window.innerHeight - estimatedHeight - 12)
    );

    return { left, top };
  }

  function openSubmenuForElement(
    key: string,
    element: HTMLElement,
    submenuItems: RoomActionMenuItem[]
  ) {
    setSubmenuState({
      key,
      items: submenuItems,
      position: buildSubmenuPosition(element, submenuItems)
    });
  }

  function renderMenuPanel(
    nextItems: RoomActionMenuItem[],
    activeSubmenuKey?: string
  ) {
    return (
      <div
        style={{
          minWidth: `${minWidth}px`,
          maxWidth: "min(320px, calc(100vw - 24px))",
          maxHeight: "min(420px, calc(100vh - 24px))",
          overflowY: "auto",
          overflowX: "hidden",
          padding: "0.45rem",
          borderRadius: "16px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.96) 0%, rgba(18, 25, 37, 0.98) 100%)",
          boxShadow:
            "0 18px 42px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.03)",
          display: "grid",
          gap: "0.2rem"
        }}
      >
        {nextItems.map((item) => {
          if (isDivider(item)) {
            return (
              <div
                key={item.key}
                style={{
                  height: "1px",
                  margin: "0.28rem 0.2rem",
                  background: "rgba(199, 210, 218, 0.12)"
                }}
              />
            );
          }

          const hasSubmenu = Array.isArray(item.submenu) && item.submenu.length > 0;
          const submenuOpen = hasSubmenu && activeSubmenuKey === item.key;

          return (
            <div
              key={item.key}
              onMouseEnter={(event) => {
                if (hasSubmenu) {
                  openSubmenuForElement(
                    item.key,
                    event.currentTarget as HTMLDivElement,
                    item.submenu ?? []
                  );
                } else if (activeSubmenuKey) {
                  setSubmenuState(null);
                }
              }}
            >
              <button
                type="button"
                disabled={item.disabled}
                title={item.disabled ? item.detail : undefined}
                onClick={(event) => {
                  if (hasSubmenu) {
                    if (submenuOpen) {
                      setSubmenuState(null);
                    } else {
                      openSubmenuForElement(
                        item.key,
                        event.currentTarget as HTMLButtonElement,
                        item.submenu ?? []
                      );
                    }
                    return;
                  }

                  item.onSelect?.();
                  onClose();
                }}
                style={{
                  width: "100%",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: "0.75rem",
                  padding: "0.7rem 0.85rem",
                  borderRadius: "12px",
                  border: "none",
                  background: submenuOpen
                    ? "linear-gradient(180deg, rgba(16, 41, 43, 0.62) 0%, rgba(18, 25, 37, 0.74) 100%)"
                    : "transparent",
                  color: item.disabled ? palette.silverMuted : palette.silver,
                  cursor: item.disabled ? "default" : "pointer",
                  opacity: item.disabled ? 0.65 : 1,
                  textAlign: "left",
                  fontSize: "0.9rem",
                  lineHeight: 1.35
                }}
              >
                <span style={{ display: "grid", gap: "0.2rem", minWidth: 0 }}>
                  <span>{item.label}</span>
                  {item.detail ? (
                    <span
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.72rem",
                        fontWeight: 400,
                        lineHeight: 1.35
                      }}
                    >
                      {item.detail}
                    </span>
                  ) : null}
                  {item.stateLabel ? (
                    <span
                      style={{
                        color: palette.teal,
                        fontSize: "0.64rem",
                        fontWeight: 700,
                        letterSpacing: "0.07em",
                        textTransform: "uppercase"
                      }}
                    >
                      {item.stateLabel}
                    </span>
                  ) : null}
                </span>
                {hasSubmenu ? (
                  <span
                    aria-hidden="true"
                    style={{
                      color: submenuOpen ? palette.teal : palette.silverMuted,
                      fontSize: "0.92rem"
                    }}
                  >
                    ›
                  </span>
                ) : null}
              </button>
            </div>
          );
        })}
      </div>
    );
  }

  return createPortal(
    <div
      ref={rootRef}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1200,
        pointerEvents: "none"
      }}
    >
      <div
        style={{
          position: "fixed",
          top: `${anchorPosition.top}px`,
          left: `${anchorPosition.left}px`,
          pointerEvents: "auto"
        }}
      >
        {renderMenuPanel(items, submenuState?.key)}
      </div>

      {submenuState ? (
        <div
          style={{
            position: "fixed",
            top: `${submenuState.position.top}px`,
            left: `${submenuState.position.left}px`,
            pointerEvents: "auto"
          }}
        >
          {renderMenuPanel(submenuState.items)}
        </div>
      ) : null}
    </div>,
    document.body
  );
}
