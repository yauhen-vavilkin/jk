// Every parameter Jenkins defines, and what JK does with it, in the order
// Jenkins declares them. All of them are listed, always:
// this is where a saved job is built, so nothing it will send is behind a click.
import { ChevronDown } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import Menu, { MenuItem } from "@/components/ui/Menu";
import Segmented from "@/components/ui/Segmented";
import { fixedStart, holdsPlaceholder, needsAValue, type Draft, type ParamRow } from "./paramRows";

// When space is short the name, the default and the value give way, each cut
// with … and whole on hover; `sent as` keeps its width, so every choice stays
// on screen.
const GRID =
  "grid grid-cols-[minmax(140px,220px)_minmax(80px,1fr)_minmax(160px,300px)_186px] gap-4";

export default function ParamTable({
  rows,
  onChange,
  onDrop,
}: {
  rows: ParamRow[];
  onChange: (name: string, setting: Partial<Draft[string]>) => void;
  onDrop: (name: string) => void;
}) {
  return (
    <div className="flex flex-col gap-0 px-7 pb-6 pt-4">
      <div
        className={`${GRID} border-b border-hairline px-3 pb-2 font-mono text-[12px] uppercase tracking-[.06em] text-dim`}
      >
        <span>parameter</span>
        <span>jenkins default</span>
        <span>your value</span>
        <span>sent as</span>
      </div>

      {rows.map((row) => (
        <div
          key={row.name}
          className={`${GRID} items-center border-b border-surface-2 px-3 py-1.5 text-[14px] ${
            row.mode === "default" && row.kind !== "removed" ? "text-dim" : ""
          }`}
        >
          <span
            title={row.name}
            className={`overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[13px] ${
              row.kind === "added"
                ? "text-ok"
                : row.kind === "removed"
                  ? "text-warn line-through"
                  : ""
            }`}
          >
            {row.name}
          </span>

          <JenkinsDefault row={row} />

          <YourValue row={row} onChange={onChange} onDrop={onDrop} />

          <SentAs row={row} onChange={onChange} />
        </div>
      ))}

    </div>
  );
}

/** What Jenkins would use. It has none for a parameter it cannot compute, so none is written. */
function JenkinsDefault({ row }: { row: ParamRow }) {
  const declared = needsAValue(row.definition) ? "" : (row.definition?.default ?? "");
  const shown = row.kind === "removed" ? "removed from Jenkins" : declared;
  return (
    <span
      className="overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[13px] text-dim"
      title={shown}
    >
      {shown}
    </span>
  );
}

function YourValue({
  row,
  onChange,
  onDrop,
}: {
  row: ParamRow;
  onChange: (name: string, setting: Partial<Draft[string]>) => void;
  onDrop: (name: string) => void;
}) {
  if (row.kind === "removed") {
    return (
      <span className="text-[13px] text-dim">
        you had <span className="font-mono line-through">{row.value || "empty"}</span> ·{" "}
        <button type="button" className="text-text" onClick={() => onDrop(row.name)}>
          drop
        </button>
      </span>
    );
  }

  if (row.mode === "ask") {
    // Jenkins' placeholder is not a value anyone typed, so it is not "last".
    const last =
      row.lastValue && !holdsPlaceholder(row.definition, row.lastValue) ? row.lastValue : null;
    if (!last) return <span />;
    return (
      <span className="flex h-8 items-center rounded-[5px] border border-dashed border-accent px-2 text-[13px] text-accent">
        <span className="overflow-hidden text-ellipsis whitespace-nowrap">
          last <span className="font-mono">{last}</span>
        </span>
      </span>
    );
  }

  if (row.mode === "default") {
    if (row.kind === "added") {
      return (
        <span className="text-[13px] text-dim">
          <button
            type="button"
            onClick={() => onChange(row.name, { mode: "fixed", value: fixedStart(row) })}
          >
            set value
          </button>
        </span>
      );
    }
    if (needsAValue(row.definition)) {
      return <span className="font-mono text-[13px] text-warn">required</span>;
    }
    return <span />;
  }

  // Jenkins declares the whole list for a plain choice parameter, so the value is
  // picked, not typed. Everything else keeps the free-text field: an Active Choices
  // parameter arrives without a list, a password carries its own note under the
  // field, and a value the list no longer holds must stay editable — a saved job
  // carries the definitions as they were, and they are replaced only when drift is
  // repaired.
  const choices = row.definition?.choices ?? [];
  const offered = !row.isPassword && (row.value === "" || choices.includes(row.value));
  if (choices.length > 0 && offered) {
    return (
      <ChoiceField
        name={row.name}
        value={row.value}
        choices={choices}
        onChange={(value) => onChange(row.name, { value })}
      />
    );
  }

  // Why Save is off is shown on the field itself, never as prose over the table.
  const refused =
    (row.isPassword && row.value.trim() === "") || holdsPlaceholder(row.definition, row.value);
  const field = (
    <ValueField
      name={row.name}
      value={row.value}
      refused={refused}
      onChange={(value) => onChange(row.name, { value })}
    />
  );

  const note = row.isPassword ? "password · sent as written" : row.value === "" ? "sent empty" : null;
  if (!note) return field;
  return (
    <span className="flex flex-col">
      {field}
      <span className="pt-0.5 text-[13px] text-dim">{note}</span>
    </span>
  );
}

function SentAs({
  row,
  onChange,
}: {
  row: ParamRow;
  onChange: (name: string, setting: Partial<Draft[string]>) => void;
}) {
  if (row.kind === "removed") return <span className="text-dim">—</span>;
  // `fixed` starts from something to send, not an empty box.
  const choose = (mode: Draft[string]["mode"]) =>
    onChange(row.name, mode === "fixed" && row.value === "" ? { mode, value: fixedStart(row) } : { mode });
  return <Segmented name={row.name} value={row.mode} onChange={choose} />;
}

/** The values Jenkins declares for a choice parameter, in the order it declares them. */
function ChoiceField({
  name,
  value,
  choices,
  onChange,
}: {
  name: string;
  value: string;
  choices: string[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);

  return (
    <span className="relative flex">
      <button
        ref={button}
        type="button"
        aria-label={`Value for ${name}, currently ${value || "not chosen"}`}
        onClick={() => setOpen((shown) => !shown)}
        className="flex h-8 w-full items-center justify-between gap-2 rounded-[5px] border border-dim px-2 font-mono text-[13px] outline-hidden focus:border-accent"
      >
        <span
          className={`overflow-hidden text-ellipsis whitespace-nowrap ${
            value ? "text-text" : "text-dim"
          }`}
        >
          {value || "choose a value"}
        </span>
        <ChevronDown size={13} aria-hidden className="flex-none text-dim" />
      </button>
      {open && (
        <Menu onClose={() => setOpen(false)} anchor={button} align="left" width={320}>
          {choices.map((choice) => (
            <MenuItem
              key={choice}
              onClick={() => {
                setOpen(false);
                onChange(choice);
              }}
            >
              <span className={choice === value ? "text-text" : ""}>{choice}</span>
            </MenuItem>
          ))}
        </Menu>
      )}
    </span>
  );
}

/**
 * A value with line breaks (a Cypress tag list, say) is edited as the lines it
 * is: a one-line field would join them and change what Jenkins receives. Once a
 * field has been a textarea it stays one, so deleting the last line break never
 * swaps the field out from under the cursor; it grows with what it holds.
 */
function ValueField({
  name,
  value,
  refused,
  onChange,
}: {
  name: string;
  value: string;
  /** The value cannot be saved: the border says so where the value is typed. */
  refused: boolean;
  onChange: (value: string) => void;
}) {
  const [multiline, setMultiline] = useState(value.includes("\n"));
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (value.includes("\n")) setMultiline(true);
  }, [value]);

  useLayoutEffect(() => {
    const box = area.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight + 2, 240)}px`;
  }, [value, multiline]);

  if (multiline) {
    return (
      <textarea
        ref={area}
        value={value}
        rows={1}
        aria-label={`Value for ${name}`}
        onChange={(event) => onChange(event.target.value)}
        className={`w-full resize-y rounded-[5px] border px-2 py-[6px] font-mono text-[13px] leading-[1.45] text-text outline-hidden focus:border-accent ${
          refused ? "border-warn" : "border-dim"
        }`}
      />
    );
  }
  return (
    <input
      value={value}
      aria-label={`Value for ${name}`}
      onChange={(event) => onChange(event.target.value)}
      className={`h-8 w-full rounded-[5px] border px-2 font-mono text-[13px] text-text outline-hidden focus:border-accent ${
        refused ? "border-warn" : "border-dim"
      }`}
    />
  );
}
