// When does this step start? The answer lives on the card it belongs to, before
// STEP N. The icon always shows; the click opens the step's condition menu only
// while the step can still change: in a draft being edited, or on a held step.
import { useDndContext } from "@dnd-kit/core";
import { useEffect, useRef, useState } from "react";

import type { Condition } from "@/api/types";
import Menu from "@/components/ui/Menu";
import {
  CONDITION_COLOUR,
  CONDITION_ICON,
  CONDITION_LABELS,
  CONDITION_ORDER,
} from "@/lib/conditions";

/** Wider than a step card, which is why the menu is placed against the window. */
const MENU_WIDTH = 286;

export default function ConditionButton({
  condition,
  editable,
  onChange,
}: {
  condition: Condition;
  editable: boolean;
  onChange: (next: Condition) => void;
}) {
  // Placed against the window, not the card: the card is narrower than the menu
  // and clips what overflows it.
  const [open, setOpen] = useState<{ left: number; top: number; above: boolean } | null>(null);
  // A press on the button is the button's own: its click opens or closes the
  // menu, whether it came from a mouse, a key or a screen reader.
  const anchor = useRef<HTMLButtonElement>(null);
  const Icon = CONDITION_ICON[condition];
  const colour = CONDITION_COLOUR[condition];
  const { active } = useDndContext();

  const toggle = (anchor: HTMLElement) => {
    if (open) return setOpen(null);
    const box = anchor.getBoundingClientRect();
    const above = box.bottom > window.innerHeight * 0.55;
    setOpen({
      // The rightmost card of a wide flow would push the menu off the window.
      left: Math.min(box.left, window.innerWidth - MENU_WIDTH - 8),
      top: above ? box.top : box.bottom,
      above,
    });
  };

  // It is placed once, against the window. A scroll leaves it behind, and a drag
  // puts a transform on the card, which becomes the frame a fixed box sits in.
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(null);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);
  useEffect(() => {
    if (active) setOpen(null);
  }, [active]);

  return (
    <span className="flex flex-none" onPointerDown={(event) => event.stopPropagation()}>
      <button
        ref={anchor}
        type="button"
        title={CONDITION_LABELS[condition]}
        aria-label={CONDITION_LABELS[condition]}
        aria-haspopup={editable ? "menu" : undefined}
        disabled={!editable}
        onClick={(event) => {
          event.stopPropagation();
          toggle(event.currentTarget);
        }}
        // No box: a box around a check reads as a ticked checkbox.
        className={`inline-flex h-6 w-6 items-center justify-center rounded-[5px] transition-colors duration-150 enabled:hover:bg-hairline ${colour.text}`}
      >
        <Icon size={13} strokeWidth={2} aria-hidden />
      </button>
      {open && (
        <div className="fixed z-30 h-0 w-0" style={{ left: open.left, top: open.top }}>
        <Menu
          onClose={() => setOpen(null)}
          align="left"
          side={open.above ? "above" : "below"}
          width={MENU_WIDTH}
          anchor={anchor}
        >
          {CONDITION_ORDER.map((item) => {
            const ItemIcon = CONDITION_ICON[item];
            return (
              <button
                key={item}
                type="button"
                role="menuitem"
                onClick={(event) => {
                  event.stopPropagation();
                  setOpen(null);
                  anchor.current?.focus();
                  if (item !== condition) onChange(item);
                }}
                className={`flex items-center gap-2.5 px-3 py-2 text-left font-sans text-[14px] transition-colors duration-150 hover:bg-surface-2 hover:text-text ${
                  item === condition ? "bg-surface-2 text-text" : "text-key"
                }`}
              >
                <ItemIcon size={15} aria-hidden className={`flex-none ${CONDITION_COLOUR[item].text}`} />
                {CONDITION_LABELS[item]}
              </button>
            );
          })}
        </Menu>
        </div>
      )}
    </span>
  );
}
