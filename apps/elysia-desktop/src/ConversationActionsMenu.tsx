import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent
} from "react";
import { createPortal } from "react-dom";

type ConversationActionsMenuProps = {
  conversationId: string;
  conversationTitle: string;
  pinned?: boolean;
  archived?: boolean;
  disabled?: boolean;
  onShare: (conversationId: string) => void;
  onRename: (conversationId: string) => void;
  onMoveToProject: (conversationId: string) => void;
  onTogglePinned: (conversationId: string, nextPinned: boolean) => void;
  onToggleArchived: (conversationId: string, nextArchived: boolean) => void;
  onDelete: (conversationId: string) => void;
};

const palette = {
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  panel: "rgba(18, 25, 37, 0.98)",
  panelRaised: "rgba(24, 33, 48, 0.96)",
  glowTeal: "rgba(126, 215, 209, 0.16)",
  glowBronze: "rgba(138, 106, 60, 0.12)"
} as const;

type MenuAction = {
  key: string;
  label: string;
  tone?: "default" | "destructive";
  onSelect: () => void;
};

type MenuPosition = {
  top: number;
  left: number;
};

const MENU_WIDTH_PX = 280;
const MENU_OFFSET_PX = 6;
const VIEWPORT_PADDING_PX = 12;
const ESTIMATED_MENU_HEIGHT_PX = 360;

export default function ConversationActionsMenu({
  conversationId,
  conversationTitle,
  pinned = false,
  archived = false,
  disabled = false,
  onShare,
  onRename,
  onMoveToProject,
  onTogglePinned,
  onToggleArchived,
  onDelete
}: ConversationActionsMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<MenuPosition>({
    top: 0,
    left: 0
  });

  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const primaryActions = useMemo<MenuAction[]>(
    () => [
      {
        key: "share",
        label: "Share",
        onSelect: () => onShare(conversationId)
      },
      {
        key: "rename",
        label: "Rename",
        onSelect: () => onRename(conversationId)
      },
      {
        key: "move-to-project",
        label: "Move to project",
        onSelect: () => onMoveToProject(conversationId)
      }
    ],
    [conversationId, onMoveToProject, onRename, onShare]
  );

  const secondaryActions = useMemo<MenuAction[]>(
    () => [
      {
        key: "pin",
        label: pinned ? "Unpin chat" : "Pin chat",
        onSelect: () => onTogglePinned(conversationId, !pinned)
      },
      {
        key: "archive",
        label: archived ? "Unarchive" : "Archive",
        onSelect: () => onToggleArchived(conversationId, !archived)
      },
      {
        key: "delete",
        label: "Delete",
        tone: "destructive",
        onSelect: () => onDelete(conversationId)
      }
    ],
    [archived, conversationId, onDelete, onToggleArchived, onTogglePinned, pinned]
  );

  useEffect(() => {
    if (disabled && isOpen) {
      setIsOpen(false);
    }
  }, [disabled, isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function updateMenuPosition() {
      const trigger = triggerRef.current;
      if (!trigger) {
        return;
      }

      const rect = trigger.getBoundingClientRect();

      let left = rect.right - MENU_WIDTH_PX;
      left = Math.max(VIEWPORT_PADDING_PX, left);
      left = Math.min(
        left,
        window.innerWidth - MENU_WIDTH_PX - VIEWPORT_PADDING_PX
      );

      const openDownTop = rect.bottom + MENU_OFFSET_PX;
      const openUpTop = rect.top - ESTIMATED_MENU_HEIGHT_PX - MENU_OFFSET_PX;

      const top =
        openDownTop + ESTIMATED_MENU_HEIGHT_PX <=
        window.innerHeight - VIEWPORT_PADDING_PX
          ? openDownTop
          : Math.max(VIEWPORT_PADDING_PX, openUpTop);

      setMenuPosition({ top, left });
    }

    function handlePointerDown(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }

      if (triggerRef.current?.contains(target)) {
        return;
      }

      if (menuRef.current?.contains(target)) {
        return;
      }

      setIsOpen(false);
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }

    function handleViewportMove() {
      updateMenuPosition();
    }

    updateMenuPosition();

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    window.addEventListener("resize", handleViewportMove);
    window.addEventListener("scroll", handleViewportMove, true);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
      window.removeEventListener("resize", handleViewportMove);
      window.removeEventListener("scroll", handleViewportMove, true);
    };
  }, [isOpen]);

  function handleToggle(event: ReactMouseEvent<HTMLButtonElement>) {
    event.stopPropagation();

    if (disabled) {
      return;
    }

    setIsOpen((current) => !current);
  }

  function handleContainerMouseDown(event: ReactMouseEvent<HTMLDivElement>) {
    event.stopPropagation();
  }

  function handleSelect(
    event: ReactMouseEvent<HTMLButtonElement>,
    action: MenuAction
  ) {
    event.stopPropagation();
    setIsOpen(false);
    action.onSelect();
  }

  const menu =
    isOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={menuRef}
            role="menu"
            aria-label={`Actions for ${conversationTitle}`}
            onMouseDown={(event) => event.stopPropagation()}
            onClick={(event) => event.stopPropagation()}
            style={{
              position: "fixed",
              top: `${menuPosition.top}px`,
              left: `${menuPosition.left}px`,
              zIndex: 9999,
              width: `${MENU_WIDTH_PX}px`,
              maxWidth: `calc(100vw - ${VIEWPORT_PADDING_PX * 2}px)`,
              padding: "0.4rem",
              borderRadius: "16px",
              border: `1px solid ${palette.lineSilver}`,
              background:
                "linear-gradient(180deg, rgba(24, 33, 48, 0.98) 0%, rgba(18, 25, 37, 0.98) 100%)",
              boxShadow:
                `0 18px 42px rgba(0,0,0,0.32), 0 0 22px ${palette.glowBronze}, inset 0 1px 0 rgba(255,255,255,0.03)`
            }}
          >
            <div
              style={{
                padding: "0.45rem 0.55rem 0.55rem 0.55rem",
                color: palette.silverMuted,
                fontSize: "0.76rem",
                lineHeight: 1.45,
                borderBottom: `1px solid rgba(199, 210, 218, 0.08)`,
                marginBottom: "0.25rem"
              }}
            >
              {conversationTitle}
            </div>

            <div style={{ display: "grid", gap: "0.18rem" }}>
              {primaryActions.map((action) => (
                <button
                  key={action.key}
                  type="button"
                  role="menuitem"
                  onClick={(event) => handleSelect(event, action)}
                  onMouseDown={(event) => event.stopPropagation()}
                  style={{
                    display: "flex",
                    width: "100%",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "0.75rem",
                    padding: "0.72rem 0.8rem",
                    borderRadius: "12px",
                    border: "1px solid transparent",
                    background: "transparent",
                    color: palette.silver,
                    cursor: "pointer",
                    textAlign: "left"
                  }}
                  onMouseEnter={(event) => {
                    event.currentTarget.style.background =
                      "linear-gradient(180deg, rgba(16, 41, 43, 0.42) 0%, rgba(18, 25, 37, 0.56) 100%)";
                    event.currentTarget.style.border = `1px solid ${palette.lineTeal}`;
                  }}
                  onMouseLeave={(event) => {
                    event.currentTarget.style.background = "transparent";
                    event.currentTarget.style.border = "1px solid transparent";
                  }}
                >
                  <span>{action.label}</span>
                </button>
              ))}
            </div>

            <div
              aria-hidden="true"
              style={{
                margin: "0.35rem 0.2rem",
                height: "1px",
                background: "rgba(199, 210, 218, 0.08)"
              }}
            />

            <div style={{ display: "grid", gap: "0.18rem" }}>
              {secondaryActions.map((action) => {
                const destructive = action.tone === "destructive";

                return (
                  <button
                    key={action.key}
                    type="button"
                    role="menuitem"
                    onClick={(event) => handleSelect(event, action)}
                    onMouseDown={(event) => event.stopPropagation()}
                    style={{
                      display: "flex",
                      width: "100%",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "0.75rem",
                      padding: "0.72rem 0.8rem",
                      borderRadius: "12px",
                      border: "1px solid transparent",
                      background: "transparent",
                      color: destructive ? "#E7B4A4" : palette.silver,
                      cursor: "pointer",
                      textAlign: "left"
                    }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.background = destructive
                        ? "linear-gradient(180deg, rgba(72, 31, 24, 0.52) 0%, rgba(18, 25, 37, 0.58) 100%)"
                        : "linear-gradient(180deg, rgba(16, 41, 43, 0.42) 0%, rgba(18, 25, 37, 0.56) 100%)";
                      event.currentTarget.style.border = destructive
                        ? `1px solid ${palette.lineBronze}`
                        : `1px solid ${palette.lineTeal}`;
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.background = "transparent";
                      event.currentTarget.style.border = "1px solid transparent";
                    }}
                  >
                    <span>{action.label}</span>
                  </button>
                );
              })}
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <>
      <div
        ref={containerRef}
        onMouseDown={handleContainerMouseDown}
        style={{
          position: "relative",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "flex-end"
        }}
      >
        <button
          ref={triggerRef}
          type="button"
          aria-label={`Conversation actions for ${conversationTitle}`}
          aria-haspopup="menu"
          aria-expanded={isOpen}
          onClick={handleToggle}
          onMouseDown={(event) => event.stopPropagation()}
          disabled={disabled}
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: "2.15rem",
            height: "2.15rem",
            borderRadius: "12px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(24, 33, 48, 0.64) 0%, rgba(18, 25, 37, 0.72) 100%)",
            color: palette.silverMuted,
            cursor: disabled ? "default" : "pointer",
            opacity: disabled ? 0.64 : 1,
            boxShadow: isOpen ? `0 0 18px ${palette.glowTeal}` : "none"
          }}
        >
          <span
            aria-hidden="true"
            style={{
              display: "grid",
              gap: "0.17rem",
              alignItems: "center",
              justifyItems: "center"
            }}
          >
            <span
              style={{
                width: "0.2rem",
                height: "0.2rem",
                borderRadius: "999px",
                background: "currentColor"
              }}
            />
            <span
              style={{
                width: "0.2rem",
                height: "0.2rem",
                borderRadius: "999px",
                background: "currentColor"
              }}
            />
            <span
              style={{
                width: "0.2rem",
                height: "0.2rem",
                borderRadius: "999px",
                background: "currentColor"
              }}
            />
          </span>
        </button>
      </div>

      {menu}
    </>
  );
}
