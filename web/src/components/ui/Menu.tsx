// A small list of actions anchored under what opened it. `esc` closes it, and so
// does a click anywhere else, and so does another menu opening.
import { useEffect, useRef, type ReactNode, type RefObject } from "react";

/** Said by every menu as it opens, so the one open before it closes. */
const OPENED = "jk:menu-opened";

export default function Menu({
  children,
  onClose,
  align = "right",
  side = "below",
  width = 260,
  anchor,
  role = "menu",
  label,
}: {
  children: ReactNode;
  onClose: () => void;
  align?: "left" | "right";
  /** Above the anchor when there is no room under it. */
  side?: "below" | "above";
  width?: number;
  /** What opened it: a press there is its opener's own, so a second click closes the menu. */
  anchor?: RefObject<HTMLElement | null>;
  /** `dialog` for details that hold no menu items. */
  role?: "menu" | "dialog";
  label?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);

  // One menu at a time, however it was opened: a click elsewhere closes the
  // last one, but a key press that opens the next does not.
  useEffect(() => {
    const self = {};
    window.dispatchEvent(new CustomEvent(OPENED, { detail: self }));
    const another = (event: Event) => {
      if ((event as CustomEvent).detail !== self) close.current();
    };
    window.addEventListener(OPENED, another);
    return () => window.removeEventListener(OPENED, another);
  }, []);

  useEffect(() => {
    const away = (event: MouseEvent) => {
      const target = event.target as Node;
      if (box.current?.contains(target) || anchor?.current?.contains(target)) return;
      onClose();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (box.current?.contains(document.activeElement)) anchor?.current?.focus();
        onClose();
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const items = [...(box.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
      if (items.length === 0) return;
      event.preventDefault();
      const at = items.indexOf(document.activeElement as HTMLElement);
      const step = event.key === "ArrowDown" ? 1 : -1;
      items[(at + step + items.length) % items.length]?.focus();
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [onClose, anchor]);

  return (
    <div
      ref={box}
      role={role}
      aria-label={label}
      // Tab out of it closes it, as a click elsewhere does.
      onBlur={(event) => {
        const next = event.relatedTarget as Node | null;
        if (next && !box.current?.contains(next) && !anchor?.current?.contains(next)) onClose();
      }}
      style={{ width }}
      className={`absolute z-30 flex flex-col ${side === "below" ? "top-full mt-2" : "bottom-full mb-2"} rounded-md border border-hairline bg-surface py-1 shadow-[0_8px_24px_rgba(0,0,0,.5)] ${
        align === "right" ? "right-0" : "left-0"
      }`}
    >
      {children}
    </div>
  );
}

export function MenuItem({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="px-3 py-2 text-left text-[14px] text-key transition-colors duration-150 hover:bg-surface-2 hover:text-text"
    >
      {children}
    </button>
  );
}
