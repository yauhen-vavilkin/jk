// The keyboard's way onto the board, and the mouse's too: a short list of saved
// jobs and saved flows under the "+" of a flow or the New flow button. A pick
// does what a drop does. The arrow keys walk the list, Enter picks, and the
// cursor stays in the field.
import { useDndContext } from "@dnd-kit/core";
import { useEffect, useId, useRef, useState } from "react";

import type { Preset, SavedFlow } from "@/api/types";
import Menu from "@/components/ui/Menu";
import { nextActive } from "@/components/Search";
import { groupByOperation, savedFlowMeta } from "./SavedJobs";

const PICKER_PLACEHOLDER = "Search saved jobs and saved flows…";
const WIDTH = 320;

export type Picked = { kind: "preset"; preset: Preset } | { kind: "saved-flow"; savedFlow: SavedFlow };

interface PickerOption {
  key: string;
  label: string;
  note: string;
  /** A saved job Jenkins changed cannot be added, as it cannot be dragged. */
  disabled: boolean;
  picked: Picked;
}

/** Saved jobs in the column's order, then saved flows; a query keeps those whose name or operation has it. */
export function pickerOptions(presets: Preset[], savedFlows: SavedFlow[], query: string): PickerOption[] {
  const needle = query.trim().toLowerCase();
  const has = (...texts: string[]) => !needle || texts.some((text) => text.toLowerCase().includes(needle));
  return [
    ...groupByOperation(presets)
      .flatMap(([, group]) => group)
      .filter((preset) => has(preset.name, preset.operation))
      .map((preset) => ({
        key: `preset:${preset.id}`,
        label: preset.name,
        note: preset.drift ? "Jenkins changed it" : preset.operation.toLowerCase(),
        disabled: preset.drift !== null,
        picked: { kind: "preset" as const, preset },
      })),
    ...savedFlows
      .filter((savedFlow) => has(savedFlow.name))
      .map((savedFlow) => ({
        key: `saved-flow:${savedFlow.id}`,
        label: savedFlow.name,
        note: savedFlowMeta(savedFlow),
        disabled: false,
        picked: { kind: "saved-flow" as const, savedFlow },
      })),
  ];
}

export default function JobPicker({
  anchor,
  label,
  presets,
  savedFlows,
  onPick,
  onClose,
}: {
  /** What opened it: the picker opens against it. */
  anchor: HTMLElement;
  /** Its name for a screen reader: "Add step" or "New flow". */
  label: string;
  presets: Preset[];
  savedFlows: SavedFlow[];
  onPick: (picked: Picked) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);
  const anchorRef = useRef<HTMLElement>(anchor);
  // Focus goes back to what opened it, as after a menu.
  const [opener] = useState(() => document.activeElement as HTMLElement | null);
  // Placed once against the window, like the other menus on the board.
  const [place] = useState(() => {
    const rect = anchor.getBoundingClientRect();
    const above = rect.bottom > window.innerHeight * 0.55;
    return {
      left: Math.max(8, Math.min(rect.left, window.innerWidth - WIDTH - 8)),
      top: above ? rect.top : rect.bottom,
      above,
    };
  });

  const options = pickerOptions(presets, savedFlows, query);
  const choices = options.filter((option) => !option.disabled);
  const marked = choices.length > 0 ? Math.min(active, choices.length - 1) : -1;
  const optionId = (key: string) => `${listId}-${key}`;

  const close = (refocus: boolean) => {
    onClose();
    if (refocus) opener?.focus();
  };
  const pick = (option: PickerOption) => {
    if (option.disabled) return;
    onPick(option.picked);
    close(true);
  };

  // A scroll of the board leaves it behind, and a drag starting elsewhere ends it.
  const { active: dragged } = useDndContext();
  useEffect(() => {
    if (dragged) onClose();
  }, [dragged, onClose]);
  useEffect(() => {
    const away = (event: Event) => {
      if (!box.current?.contains(event.target as Node)) onClose();
    };
    window.addEventListener("scroll", away, true);
    window.addEventListener("resize", away);
    return () => {
      window.removeEventListener("scroll", away, true);
      window.removeEventListener("resize", away);
    };
  }, [onClose]);

  return (
    <div ref={box} className="fixed z-30 h-0 w-0" style={{ left: place.left, top: place.top }}>
      <Menu
        onClose={onClose}
        align="left"
        side={place.above ? "above" : "below"}
        width={WIDTH}
        anchor={anchorRef}
        role="dialog"
        label={label}
      >
        <input
          autoFocus
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              close(true);
            } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setActive(nextActive(marked, choices.length, event.key));
            } else if (event.key === "Enter" && marked >= 0) {
              event.preventDefault();
              pick(choices[marked]!);
            }
          }}
          placeholder={PICKER_PLACEHOLDER}
          aria-label={PICKER_PLACEHOLDER}
          role="combobox"
          aria-expanded
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={marked >= 0 ? optionId(choices[marked]!.key) : undefined}
          className="mx-2 mb-1 mt-1 h-8 rounded-md border border-dim bg-well px-2.5 text-[14px] caret-accent outline-hidden focus:border-accent"
        />
        <div id={listId} role="listbox" aria-label={label} className="flex max-h-[320px] flex-col overflow-auto">
          {options.length === 0 && <div className="px-3 py-2 text-[14px] text-dim">Nothing matches that.</div>}
          {options.map((option) => {
            const isMarked = marked >= 0 && choices[marked] === option;
            return (
              <div
                key={option.key}
                id={optionId(option.key)}
                role="option"
                aria-selected={isMarked}
                aria-disabled={option.disabled || undefined}
                // The cursor stays in the field, so a click does not end the search first.
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => !option.disabled && setActive(choices.indexOf(option))}
                onClick={() => pick(option)}
                className={`flex items-baseline justify-between gap-3 px-3 py-1.5 text-[14px] ${
                  option.disabled ? "cursor-default text-dim" : "cursor-pointer"
                } ${isMarked ? "bg-surface-2" : ""}`}
              >
                <span className="truncate">{option.label}</span>
                <span
                  className={`shrink-0 ${option.disabled ? "text-[13px] text-warn" : "font-mono text-[12px] text-dim"}`}
                >
                  {option.note}
                </span>
              </div>
            );
          })}
        </div>
      </Menu>
    </div>
  );
}
