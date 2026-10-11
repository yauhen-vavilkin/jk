// The one row that says what a flow is doing and what can be done about it.
// Buttons, not menus: Run, Stop, Resume, edit, save as flow, duplicate, remove.
import { Bookmark, Check, Copy, Pencil, Pin, PinOff, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Drift, Flow, SavedFlow, Step } from "@/api/types";
import IconButton from "@/components/ui/IconButton";
import InlineConfirm from "@/components/ui/InlineConfirm";
import { SAVE, SAVED, SAVING } from "@/components/ui/SaveButton";
import StatusIcon from "@/components/ui/StatusIcon";
import {
  DangerButton,
  PrimaryButton,
  QuietButton,
  SecondaryButton,
} from "@/components/ui/primitives";
import { hasEnded } from "@/lib/flowState";
import {
  changedJobsOf,
  fillLabel,
  fillNextTitle,
  headerMetaOf,
  headerStateOf,
  removeWaitsFor,
  reviewJobsLabel,
  saveStateOf,
  stopChoices,
  trashAction,
  undecidedStep,
} from "./headerState";

export const STOP_FIRST = "Stop the flow first";
export const RUN_NEEDS_READY = "Press Done to run";
export const UNREACHABLE = "Jenkins is unreachable";
// A draft never ran, so it is gone; a flow that ran leaves only the board.
export const REMOVE_DRAFT = "Delete this draft. History does not keep it.";
export const REMOVE_RAN = "Remove from the board. History keeps it.";
export const EDIT_ENDED = "Replace with an editable copy";
/** Wide enough for `Saving…`, so the buttons beside Save stay where they are. */
const SAVE_WIDTH = 96;

/** Where focus goes back to when an in-place choice, or the name field, closes. */
type FocusBack = "name" | "stop" | "remove" | null;

export default function FlowHeader({
  flow,
  canReview,
  onReview,
  onStop,
  onResume,
  onRename,
  onSaveAsFlow,
  onDelete,
  onOpenAttention,
  onReviewHeld,
  onRunAgain,
  onEdit,
  onDuplicate,
  onPin,
  busy,
  keptAs,
  saving,
  unfilled = 0,
  nextToFill = 0,
  onFillNext,
  driftOf,
  startRenaming = false,
}: {
  flow: Flow;
  /** Jenkins can be reached. */
  canReview: boolean;
  /** A copy is being made. Pressed twice in a row, these would make two. */
  busy: boolean;
  onReview: () => void;
  onStop: (abort: boolean) => void;
  onResume: (fromPosition?: number) => void;
  onRename: (name: string) => void;
  onSaveAsFlow: () => void;
  onDelete: () => void;
  /** Opens Needs attention on the step that waits for a decision. */
  onOpenAttention: () => void;
  onReviewHeld: () => void;
  /** The same flow as a fresh copy, ready to run; what ran goes to History. */
  onRunAgain: () => void;
  /** Turns editing on or off. On a flow that ended it replaces it with a copy to change. */
  onEdit: (editing: boolean) => void;
  /** A second flow with the same steps, under a free name. */
  onDuplicate: () => void;
  onPin: (pinned: boolean) => void;
  /** The saved flow this one is kept as, if it still exists. */
  keptAs: SavedFlow | null;
  /** Its Save is on its way. */
  saving: boolean;
  /** Values asked at launch still empty: until they are filled it cannot start. */
  unfilled?: number;
  /** The position of the first step with one of them. */
  nextToFill?: number;
  /** Opens that step's values. */
  onFillNext?: () => void;
  /** What Jenkins changed in a step's saved job, if anything: until it is reviewed, a draft cannot run. */
  driftOf?: (step: Step) => Drift | null;
  /** Opens the name for typing once this turns true, as for a copy just made. */
  startRenaming?: boolean;
}) {
  const navigate = useNavigate();
  const changed = flow.status === "draft" && driftOf ? changedJobsOf(flow, driftOf) : [];
  const state = headerStateOf(flow, unfilled, changed.length);
  const [stopping, setStopping] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [focusBack, setFocusBack] = useState<FocusBack>(null);

  useEffect(() => {
    if (startRenaming) setRenaming(true);
  }, [startRenaming]);
  // The control named here took the focus as it appeared; that is all it was for.
  useEffect(() => {
    if (focusBack) setFocusBack(null);
  }, [focusBack]);

  const going = flow.status === "running" || flow.status === "needs_attention";
  // A stopped or failed flow's Resume review covers its held steps, so only a
  // flow that is going offers a review of its own for them.
  const held = going && flow.steps.some((step) => step.held);
  const undecided = undecidedStep(flow);
  const trash = trashAction(flow);
  const choices = stopChoices(flow);
  const meta = headerMetaOf(flow);
  const save = saveStateOf(flow, keptAs, saving);
  const firstChanged = changed[0];

  return (
    <div className="flex min-h-8 flex-wrap items-center gap-x-3.5 gap-y-2 pb-3.5">
      {/* Name and status stay on one line; the name gives way first, and the
          buttons move under it when they no longer fit beside it. */}
      <div className="flex min-w-0 flex-auto items-center gap-3.5 whitespace-nowrap">
        <span className="inline-flex flex-none">
          <StatusIcon
            name={state.glyph}
            className={`${state.tone} ${state.pulse ? "jk-pulse" : ""}`}
          />
        </span>

        {renaming ? (
          <input
            autoFocus
            defaultValue={flow.name}
            aria-label="Flow name"
            size={flow.name.length + 4}
            className="min-w-0 max-w-full border-b border-hairline font-semibold outline-hidden focus:border-accent"
            // Typing replaces the name; Enter keeps it as it is.
            onFocus={(event) => event.currentTarget.select()}
            onBlur={(event) => {
              const wanted = event.target.value.trim();
              setRenaming(false);
              if (wanted && wanted !== flow.name) onRename(wanted);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                // Without this the same Enter presses the name button that takes the focus back.
                event.preventDefault();
                setFocusBack("name");
                event.currentTarget.blur();
              }
              if (event.key === "Escape") {
                setFocusBack("name");
                setRenaming(false);
              }
            }}
          />
        ) : (
          <h2 className="flex min-w-0 font-semibold">
            {flow.editing ? (
              <button
                type="button"
                title="Rename"
                autoFocus={focusBack === "name"}
                className="cursor-text truncate"
                onClick={() => setRenaming(true)}
              >
                {flow.name}
              </button>
            ) : (
              // A flow keeps the name it was built, or ran, under: editing renames it.
              <span className="truncate" title={flow.name}>
                {flow.name}
              </span>
            )}
          </h2>
        )}

        {state.word && (
          <span className={`flex-none font-mono text-[13px] ${state.tone}`}>{state.word}</span>
        )}
        {meta && <span className="flex-none font-mono text-[13px] text-dim">{meta}</span>}
      </div>

      <div className="ml-auto flex flex-none items-center gap-2">
        {stopping ? (
          // Two clicks, no menu: the second click is the confirmation, and each
          // label says exactly what it does.
          <>
            <SecondaryButton
              onClick={() => {
                setStopping(false);
                setFocusBack("stop");
                onStop(false);
              }}
            >
              {choices.stop}
            </SecondaryButton>
            {choices.abort && (
              <DangerButton
                onClick={() => {
                  setStopping(false);
                  setFocusBack("stop");
                  onStop(true);
                }}
              >
                {choices.abort}
              </DangerButton>
            )}
            <QuietButton
              autoFocus
              onClick={() => {
                setStopping(false);
                setFocusBack("stop");
              }}
            >
              {/* Nothing runs while a step waits for a decision. */}
              {flow.status === "needs_attention" ? "Cancel" : "Keep running"}
            </QuietButton>
          </>
        ) : deleting ? (
          <InlineConfirm
            question="Remove from the board?"
            confirmLabel="Remove"
            cancelLabel="Keep"
            onConfirm={() => {
              setDeleting(false);
              onDelete();
            }}
            onCancel={() => {
              setDeleting(false);
              setFocusBack("remove");
            }}
          />
        ) : (
          <>
            {flow.status === "draft" &&
              (!flow.editing && unfilled > 0 ? (
                // Opens the first step with a value still empty.
                // Filling asks Jenkins for nothing, so it stays on when Jenkins is away.
                <PrimaryButton onClick={() => onFillNext?.()} title={fillNextTitle(nextToFill)}>
                  {fillLabel(unfilled)}
                </PrimaryButton>
              ) : !flow.editing && firstChanged ? (
                // Filled, but a saved job changed in Jenkins: it leads to the first one.
                <PrimaryButton
                  onClick={() => navigate(`/library/${firstChanged.preset_id}`)}
                  title={`Opens ${firstChanged.preset_name} in Library`}
                >
                  {reviewJobsLabel(changed.length)}
                </PrimaryButton>
              ) : (
                // Off while the flow is being edited; the title says why.
                <PrimaryButton
                  onClick={onReview}
                  disabled={!canReview || flow.editing}
                  focusable
                  title={flow.editing ? RUN_NEEDS_READY : canReview ? undefined : UNREACHABLE}
                >
                  Run
                </PrimaryButton>
              ))}
            {hasEnded(flow) && (
              <PrimaryButton
                onClick={onRunAgain}
                disabled={!canReview || busy}
                focusable
                title={canReview ? undefined : UNREACHABLE}
              >
                Run again
              </PrimaryButton>
            )}
            {held && (
              <PrimaryButton
                onClick={onReviewHeld}
                disabled={!canReview}
                focusable
                title={canReview ? undefined : UNREACHABLE}
              >
                Review added steps
              </PrimaryButton>
            )}
            {/* Nothing moves on until the user links the build or ends the flow. */}
            {undecided && (
              <PrimaryButton onClick={onOpenAttention}>
                Resolve step {undecided.position + 1}
              </PrimaryButton>
            )}
            {going && (
              <SecondaryButton autoFocus={focusBack === "stop"} onClick={() => setStopping(true)}>
                Stop
              </SecondaryButton>
            )}
            {flow.status === "stopped" && !undecided && (
              <SecondaryButton onClick={() => onResume()}>Resume</SecondaryButton>
            )}
            {flow.status === "failed" && flow.failed_at_position !== null && (
              <SecondaryButton onClick={() => onResume(flow.failed_at_position ?? undefined)}>
                Resume from step {flow.failed_at_position + 1}
              </SecondaryButton>
            )}
            {/* Editing asks Jenkins for nothing, so it stays on when Jenkins is away. */}
            {(flow.status === "draft" || hasEnded(flow)) && (
              <IconButton
                icon={Pencil}
                // On a draft it is a switch, and its word says where the next click
                // goes; on a flow that ended it makes a copy in its place.
                label={flow.editing ? "Done" : "Edit"}
                title={hasEnded(flow) ? EDIT_ENDED : undefined}
                active={flow.editing}
                quiet
                disabled={busy}
                onClick={() => onEdit(!flow.editing)}
              />
            )}
            <IconButton
              icon={flow.pinned ? PinOff : Pin}
              label={flow.pinned ? "Unpin" : "Pin"}
              active={flow.pinned}
              quiet
              onClick={() => onPin(!flow.pinned)}
            />
            <IconButton
              icon={save === "saved" ? Check : Bookmark}
              label={save === "saving" ? SAVING : save === "saved" ? SAVED : SAVE}
              title={save === "saved" ? `Saved as "${keptAs?.name ?? ""}"` : undefined}
              // Lit only while there is something to keep; after a save it reads
              // Saved until the steps change again.
              active={save === "changed"}
              muted={save === "saving" || save === "saved"}
              quiet
              minWidth={SAVE_WIDTH}
              onClick={onSaveAsFlow}
            />
            <IconButton icon={Copy} label="Duplicate" quiet disabled={busy} onClick={onDuplicate} />
            <IconButton
              icon={X}
              label="Remove"
              title={
                trash === "disabled"
                  ? (removeWaitsFor(flow) ?? STOP_FIRST)
                  : trash === "delete"
                    ? REMOVE_DRAFT
                    : REMOVE_RAN
              }
              disabled={trash === "disabled"}
              quiet
              autoFocus={focusBack === "remove"}
              // A draft and a flow that ended go at once; a stopped one asks, because
              // it still has steps that never started.
              onClick={() => (flow.status === "stopped" ? setDeleting(true) : onDelete())}
            />
          </>
        )}
      </div>
    </div>
  );
}
