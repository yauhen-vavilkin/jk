// The left column: saved jobs grouped by operation, saved flows last. It never
// renders blank.
import { useDraggable } from "@dnd-kit/core";
import {
  Bookmark,
  Copy,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type Ref } from "react";
import { useNavigate } from "react-router-dom";

import type { Preset, SavedFlow } from "@/api/types";
import { useDeleteSavedFlow, useDuplicateSavedFlow, useRenameSavedFlow } from "@/api/queries";
import InlineConfirm from "@/components/ui/InlineConfirm";
import { GroupLabel, PrimaryButton } from "@/components/ui/primitives";
import { roundMinutes } from "@/lib/time";
import PresetCard from "./PresetCard";

/** The column's own switch: a button of its own, never the label beside it. */
export function RailToggle({ open, onClick }: { open: boolean; onClick: () => void }) {
  const Icon = open ? PanelLeftClose : PanelLeftOpen;
  const title = open ? "Hide saved jobs" : "Show saved jobs";
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-expanded={open}
      onClick={onClick}
      className="inline-flex flex-none cursor-pointer rounded-md p-1 text-dim transition-colors duration-150 hover:text-text"
    >
      <Icon size={16} aria-hidden />
    </button>
  );
}

/** A group inside saved jobs: quieter than the section labels, and set in under them. */
function OperationLabel({ children }: { children: string }) {
  return <div className="pl-3 font-mono text-[12px] text-dim">{children}</div>;
}

export function groupByOperation(presets: Preset[]): [string, Preset[]][] {
  const groups = new Map<string, Preset[]>();
  for (const preset of presets) {
    const key = preset.operation.toLowerCase();
    groups.set(key, [...(groups.get(key) ?? []), preset]);
  }
  // By name only, so a card never moves because it just ran.
  for (const list of groups.values()) list.sort((left, right) => left.name.localeCompare(right.name));
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
}

/** Where the board scrolls a saved flow to after a Save. */
export const savedFlowRowId = (id: string) => `saved-flow-${id}`;

/** "6 steps · ~42m": the time only when Jenkins has a guess for every step. */
export function savedFlowMeta(savedFlow: SavedFlow): string {
  const count = savedFlow.steps.length;
  const steps = `${count} ${count === 1 ? "step" : "steps"}`;
  return savedFlow.estimate_ms ? `${steps} · ~${roundMinutes(savedFlow.estimate_ms)}` : steps;
}

function SavedFlowRow({
  savedFlow,
  problem,
  onProblem,
}: {
  savedFlow: SavedFlow;
  /** Why the last thing done to this row was refused, if it was. */
  problem: string | null;
  onProblem: (why: string | null) => void;
}) {
  const draggable = useDraggable({ id: `saved-flow:${savedFlow.id}` });
  const rename = useRenameSavedFlow();
  const duplicate = useDuplicateSavedFlow();
  const remove = useDeleteSavedFlow();
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // After a rename or a Keep, focus goes back to the button that started it.
  const renameButton = useRef<HTMLButtonElement>(null);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const [refocus, setRefocus] = useState<"rename" | "delete" | null>(null);
  useEffect(() => {
    if (!refocus) return;
    (refocus === "rename" ? renameButton : deleteButton).current?.focus();
    setRefocus(null);
  }, [refocus]);
  const said = {
    onSuccess: () => onProblem(null),
    onError: (error: Error) => onProblem(error.message),
  };
  // The row is a drag handle, so a press on a control of its own must not start one.
  const own = { onPointerDown: (event: { stopPropagation: () => void }) => event.stopPropagation() };
  // Under the row it is about, not at the top of the list: the column scrolls,
  // and a long one would carry the top out of view.
  const note = problem && <span className="px-1 text-[13px] text-warn">{problem}</span>;
  const mark = <Bookmark size={14} aria-hidden className="mt-1 flex-none text-dim" />;
  // Two lines, then cut: a copy's name differs at its end.
  const name = (
    <span title={savedFlow.name} className="line-clamp-2 break-words">
      {savedFlow.name}
    </span>
  );

  if (deleting) {
    // The name stays, so it is clear which one; the question takes the line under it.
    return (
      <>
        <div className="flex flex-col gap-1.5 rounded-md bg-surface px-3 py-2">
          <span className="inline-flex min-w-0 items-start gap-2">
            {mark}
            {name}
          </span>
          <span className="pl-[22px]">
            <InlineConfirm
              question="Delete?"
              confirmLabel="Delete"
              cancelLabel="Keep"
              onConfirm={() => {
                setDeleting(false);
                // Not `mutate(..., said)`: the row is gone before the delete settles,
                // and a component that has gone hears none of its own callbacks.
                remove.mutateAsync({ id: savedFlow.id }).then(
                  () => onProblem(null),
                  (error: Error) => onProblem(error.message),
                );
              }}
              onCancel={() => {
                setDeleting(false);
                setRefocus("delete");
              }}
            />
          </span>
        </div>
        {note}
      </>
    );
  }

  return (
    <>
      <div
        ref={draggable.setNodeRef}
        id={savedFlowRowId(savedFlow.id)}
        style={{ opacity: draggable.isDragging ? 0.4 : 1 }}
        // Only the pointer listeners: its buttons are the Tab stops, and dnd-kit's
        // own role and "press space" hints describe no key that works here.
        {...draggable.listeners}
        className="group flex cursor-grab flex-col gap-0.5 rounded-md bg-surface px-3 py-2 transition-colors duration-150 hover:bg-surface-2"
      >
        <span className="inline-flex min-w-0 items-start gap-2">
          {mark}
          {renaming ? (
            <input
              autoFocus
              defaultValue={savedFlow.name}
              aria-label="Saved flow name"
              className="min-w-0 border-b border-hairline outline-hidden focus:border-accent"
              {...own}
              onBlur={(event) => {
                const wanted = event.target.value.trim();
                setRenaming(false);
                if (wanted && wanted !== savedFlow.name) rename.mutate({ id: savedFlow.id, name: wanted }, said);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  // Without this the same Enter presses the rename button that takes the focus back.
                  event.preventDefault();
                  event.currentTarget.blur();
                }
                if (event.key === "Escape") setRenaming(false);
                if (event.key === "Enter" || event.key === "Escape") setRefocus("rename");
              }}
            />
          ) : (
            name
          )}
        </span>

        {/* Under the name, so the name has the whole width; the controls take the
            end of this line, so the row never grows, and the line gives way to them. */}
        <span className="flex items-center justify-between gap-2">
          <span className="min-w-0 truncate font-mono text-[13px] text-dim">
            {savedFlowMeta(savedFlow)}
          </span>
          {/* Tab reaches them too: they show on the same group's focus. */}
          <span className="flex flex-none items-center gap-1 opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100">
            <RowButton
              icon={Pencil}
              title="Rename saved flow"
              buttonRef={renameButton}
              {...own}
              onClick={() => setRenaming(true)}
            />
            <RowButton
              icon={Copy}
              title="Duplicate saved flow"
              {...own}
              onClick={() => duplicate.mutate({ id: savedFlow.id }, said)}
            />
            <RowButton
              icon={Trash2}
              title="Delete saved flow"
              danger
              buttonRef={deleteButton}
              {...own}
              onClick={() => setDeleting(true)}
            />
          </span>
        </span>
      </div>
      {note}
    </>
  );
}

function RowButton({
  icon: Icon,
  title,
  danger = false,
  buttonRef,
  onClick,
  onPointerDown,
}: {
  icon: LucideIcon;
  title: string;
  danger?: boolean;
  buttonRef?: Ref<HTMLButtonElement>;
  onClick: () => void;
  onPointerDown: (event: { stopPropagation: () => void }) => void;
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      title={title}
      aria-label={title}
      onPointerDown={onPointerDown}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className={`inline-flex cursor-pointer p-0.5 transition-colors duration-150 ${
        danger ? "text-dim hover:text-warn" : "text-dim hover:text-text"
      }`}
    >
      <Icon size={14} aria-hidden />
    </button>
  );
}

export default function SavedJobs({
  presets,
  savedFlows,
  onCollapse,
  problem,
  onProblem,
}: {
  presets: Preset[];
  savedFlows: SavedFlow[];
  onCollapse: () => void;
  /** The board's last refusal, when it was about one of these rows. */
  problem: { row: string; text: string } | null;
  /** A row was refused (a reason), or something done to it worked (null). */
  onProblem: (row: string, why: string | null) => void;
}) {
  const groups = groupByOperation(presets);
  const navigate = useNavigate();

  return (
    <aside
      aria-label="Saved jobs"
      className="flex flex-col gap-4 overflow-auto border-r border-hairline px-4 pb-3.5 pt-4"
    >
      <div className="flex flex-col gap-3">
        {/* The same label as saved flows below; the operations are groups inside it. */}
        <div className="flex items-center justify-between gap-2">
          <GroupLabel>saved jobs</GroupLabel>
          <RailToggle open onClick={onCollapse} />
        </div>

        {presets.length === 0 && (
          <div className="flex flex-col items-start gap-3 px-1">
            <span className="text-[14px] text-dim">
              No saved jobs yet. Pick a Jenkins job in the Library and save your values.
            </span>
            <PrimaryButton onClick={() => navigate("/library")}>Open Library</PrimaryButton>
          </div>
        )}

        {groups.map(([operation, group]) => (
          <div key={operation} className="flex flex-col gap-1.5">
            {/* No operation: under the label alone, not under an empty one. */}
            {operation && <OperationLabel>{operation}</OperationLabel>}
            {group.map((preset) => (
              <PresetCard key={preset.id} preset={preset} />
            ))}
          </div>
        ))}
      </div>

      {savedFlows.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <GroupLabel>saved flows</GroupLabel>
          {savedFlows.map((savedFlow) => (
            <SavedFlowRow
              key={savedFlow.id}
              savedFlow={savedFlow}
              problem={problem?.row === savedFlow.id ? problem.text : null}
              onProblem={(why) => onProblem(savedFlow.id, why)}
            />
          ))}
        </div>
      )}
    </aside>
  );
}
