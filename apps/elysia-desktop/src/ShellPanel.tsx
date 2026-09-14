import { useEffect, useRef, useState, type ReactNode } from "react";

// Shell columns yield space before they can crush a working room. Room-level
// layout uses its own container width, not the outer desktop width.
export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

export default function ShellPanel({ compact, open, onClose, label, side, children }: {
  compact: boolean; open: boolean; onClose: () => void;
  label: string; side: "left" | "right"; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!compact) return;
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [compact, open]);
  if (!compact) return <div className={`elysia-shell-panel elysia-shell-panel-${side}`}>{children}</div>;
  return <dialog ref={dialog} aria-label={label} className={`elysia-panel-dialog elysia-panel-dialog-${side}`}
    onClose={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="elysia-panel-dialog-content">
      <button type="button" className="elysia-shell-toggle" onClick={onClose}>Close {label}</button>
      {children}
    </div>
  </dialog>;
}
