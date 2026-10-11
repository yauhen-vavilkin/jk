// One modal at a time, over a board that stays visible behind it. `esc` closes
// it and nothing is sent; focus stays inside while it is open, starts on the
// field marked `data-autofocus` if there is one, and goes back to what opened
// the modal once it closes.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/** How long the close animation (`jk-modal-out` in index.css) runs; keep the two equal. */
const OUT_MS = 120;

export default function Modal({
  width,
  top,
  onClose,
  children,
  label,
  locked = false,
}: {
  width: number;
  top: number;
  onClose: () => void | Promise<void>;
  children: ReactNode;
  label: string;
  /** While true, `esc` and a click outside do nothing. */
  locked?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [closing, setClosing] = useState(false);
  // Read while rendering, before a field inside takes the focus.
  const [opener] = useState(() => document.activeElement as HTMLElement | null);
  // The parent passes a new onClose on every render; the listeners below are set
  // up once, so a board refresh never moves focus out of a field being typed in.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const lockedRef = useRef(locked);
  lockedRef.current = locked;
  const close = useCallback(() => {
    if (lockedRef.current) return;
    setClosing(true);
    window.setTimeout(async () => {
      try {
        await onCloseRef.current();
      } finally {
        // An asynchronous cancellation can fail and leave the dialog open.
        setClosing(false);
      }
    }, OUT_MS);
  }, []);

  useEffect(() => {
    if (box.current && !box.current.contains(document.activeElement)) {
      (box.current.querySelector<HTMLElement>("[data-autofocus]") ?? box.current).focus();
    }
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        close();
        return;
      }
      if (event.key !== "Tab" || !box.current) return;
      const focusable = box.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", key, true);
    return () => {
      document.removeEventListener("keydown", key, true);
      opener?.focus();
    };
  }, [close, opener]);

  return (
    <div className="fixed inset-0 z-50">
      <div
        className={`${closing ? "jk-backdrop-out" : "jk-backdrop-in"} absolute inset-0 bg-[rgba(12,12,14,.55)]`}
        onClick={close}
        aria-hidden
      />
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        // Centred by `left`, not by a transform, so the rise animation's own
        // transform cannot move it sideways.
        style={{
          width,
          top,
          left: `calc(50% - ${width / 2}px)`,
          boxShadow: "0 24px 64px rgba(0, 0, 0, .6)",
        }}
        className={`${closing ? "jk-modal-out" : "jk-modal-in"} absolute flex max-h-[calc(100vh-80px)] flex-col rounded-[10px] border border-hairline bg-bg outline-hidden`}
      >
        {children}
      </div>
    </div>
  );
}
