// The flow's less frequent actions, behind one quiet button, so the header keeps
// a single main action: pin, save as a saved flow, duplicate, edit a copy of a
// run that ended, and remove from the board.
import { Ellipsis } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import Menu, { MenuItem } from "@/components/ui/Menu";
import { SAVE, SAVED, SAVING } from "@/components/ui/SaveButton";

export const MORE = "More actions";

export interface FlowMenuItems {
  pinned: boolean;
  onPin: (pinned: boolean) => void;
  /** What Save would do now: see `saveStateOf`. */
  save: "new" | "changed" | "saving" | "saved";
  /** The saved flow this one is kept as, when Save reads Saved. */
  keptName?: string;
  onSave: () => void;
  onDuplicate: () => void;
  /** Only on a flow that ended: replaces it with a copy to change. */
  onEditCopy?: () => void;
  /** Why Remove waits, when it cannot remove now. */
  removeWaits?: string;
  /** Says what Remove does, as the button's title used to. */
  removeTitle: string;
  onRemove: () => void;
  /** A copy is being made: Duplicate and Edit a copy would make two. */
  busy: boolean;
}

export default function FlowMenu({
  items,
  autoFocus = false,
}: {
  items: FlowMenuItems;
  /** Takes the focus as it appears: after Remove's question on the header is kept. */
  autoFocus?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLSpanElement>(null);

  // The first item takes the focus, so the arrow keys and Enter work at once.
  useEffect(() => {
    if (open) box.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  }, [open]);

  const choose = (action: () => void) => () => {
    setOpen(false);
    opener.current?.focus();
    action();
  };

  return (
    <span ref={box} className="relative inline-flex">
      <button
        ref={opener}
        type="button"
        aria-label={MORE}
        title={MORE}
        aria-haspopup="menu"
        aria-expanded={open}
        autoFocus={autoFocus}
        onClick={() => setOpen((was) => !was)}
        className="inline-flex h-8 w-8 flex-none items-center justify-center rounded-md text-key transition-colors duration-150 hover:text-text"
      >
        <Ellipsis size={16} strokeWidth={2} aria-hidden />
      </button>
      {open && (
        <Menu onClose={() => setOpen(false)} anchor={opener} width={240} label={MORE}>
          <MenuItem onClick={choose(() => items.onPin(!items.pinned))}>
            {items.pinned ? "Unpin" : "Pin"}
          </MenuItem>
          <MenuItem
            onClick={choose(items.onSave)}
            disabled={items.save === "saving" || items.save === "saved"}
            why={
              items.save === "saved" && items.keptName
                ? `As "${items.keptName}"`
                : items.save === "changed"
                  ? "Has changes not saved yet"
                  : undefined
            }
          >
            {items.save === "saving" ? SAVING : items.save === "saved" ? SAVED : SAVE}
          </MenuItem>
          <MenuItem onClick={choose(items.onDuplicate)} disabled={items.busy}>
            Duplicate
          </MenuItem>
          {items.onEditCopy && (
            <MenuItem onClick={choose(items.onEditCopy)} disabled={items.busy}>
              Edit a copy
            </MenuItem>
          )}
          <MenuItem
            onClick={choose(items.onRemove)}
            disabled={items.removeWaits !== undefined}
            why={items.removeWaits ?? items.removeTitle}
          >
            Remove
          </MenuItem>
        </Menu>
      )}
    </span>
  );
}
