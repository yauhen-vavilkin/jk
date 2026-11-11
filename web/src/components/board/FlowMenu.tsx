// The flow's less frequent actions, behind one quiet button, so the header keeps
// a single main action: save as a saved flow, duplicate, and edit a copy of a run
// that ended. Pin and Remove are icons beside it. The menu lists only what can be
// done now: a saved flow with nothing new has no Save.
import { Ellipsis } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import Menu, { MenuItem } from "@/components/ui/Menu";
import { SAVE, SAVING } from "@/components/ui/SaveButton";

export const MORE = "More actions";
export const SAVE_CHANGES = "Save changes";

export interface FlowMenuItems {
  /** What Save would do now: see `saveStateOf`. */
  save: "new" | "changed" | "saving" | "saved";
  onSave: () => void;
  onDuplicate: () => void;
  /** Only on a flow that ended: replaces it with a copy to change. */
  onEditCopy?: () => void;
  /** A copy is being made: Duplicate and Edit a copy would make two. */
  busy: boolean;
}

export default function FlowMenu({ items }: { items: FlowMenuItems }) {
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
        onClick={() => setOpen((was) => !was)}
        className="inline-flex h-8 w-8 flex-none items-center justify-center rounded-md text-key transition-colors duration-150 hover:text-text"
      >
        <Ellipsis size={16} strokeWidth={2} aria-hidden />
      </button>
      {open && (
        <Menu onClose={() => setOpen(false)} anchor={opener} width={240} label={MORE}>
          {items.save !== "saved" && (
            <MenuItem onClick={choose(items.onSave)} disabled={items.save === "saving"}>
              {items.save === "saving" ? SAVING : items.save === "changed" ? SAVE_CHANGES : SAVE}
            </MenuItem>
          )}
          <MenuItem onClick={choose(items.onDuplicate)} disabled={items.busy}>
            Duplicate
          </MenuItem>
          {items.onEditCopy && (
            <MenuItem onClick={choose(items.onEditCopy)} disabled={items.busy}>
              Edit a copy
            </MenuItem>
          )}
        </Menu>
      )}
    </span>
  );
}
