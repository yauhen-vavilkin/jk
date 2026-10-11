// The board: saved jobs on the left, flows in the middle. Dragging a saved job
// onto a flow adds a step; dropping it below every flow starts a new one. The
// "+" of a flow and the New flow button do the same from a list.
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  type CollisionDetection,
  type DragEndEvent,
  type DragMoveEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useEffect, useRef, useState } from "react";
import { Bookmark, Plus } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import type { Flow, Preset, ReviewScope, SavedFlow, Step } from "@/api/types";
import {
  useAddStep,
  useClearFlow,
  useCloseFlow,
  useCreateFlow,
  useDeleteFlow,
  useFlows,
  useInstantiateSavedFlow,
  useJenkinsStatus,
  useLinkBuild,
  usePatchStep,
  usePinFlow,
  useSetEditing,
  useDuplicateFlow,
  useRerunFlow,
  usePresets,
  useRemoveStep,
  useRenameFlow,
  useConfirmHeld,
  useResumeFlow,
  useSaveAsFlow,
  useSavedFlows,
  useSavingFlows,
  useStartFlow,
  useStopFlow,
} from "@/api/queries";
import type { RunAgainState } from "@/components/history/History";
import NeedsAttention from "@/components/modals/NeedsAttention";
import ReviewRun from "@/components/modals/ReviewRun";
import RunValues, { carriedValues } from "@/components/modals/RunValues";
import IconButton from "@/components/ui/IconButton";
import { GroupLabel, QuietButton } from "@/components/ui/primitives";
import { CARD_CLASS } from "./cardMetrics";
import { hasEnded } from "@/lib/flowState";
import { boardAnnouncements, landed, type Landing } from "./announcements";
import { trashAction } from "./headerState";
import { insertTarget, type InsertPlace } from "./insertTarget";
import FlowSection from "./FlowSection";
import JobPicker, { type Picked } from "./JobPicker";
import NewFlowRow from "./NewFlowRow";
import { PresetCardBody } from "./PresetCard";
import SavedJobs, { RailToggle, savedFlowRowId } from "./SavedJobs";
import { StepCardBody } from "./StepCard";
import { useRail } from "./useRail";
import { visibleFlows } from "./visibleFlows";

/** How long Remove can be undone; a draft is deleted only then. */
const UNDO_MS = 8000;
/** How long a flow the board was opened at stays lit. */
const HIGHLIGHT_MS = 1500;

/**
 * Everything lands where the pointer is, never where the dragged card's
 * rectangle happens to overlap most. A saved job or a saved flow can land on a
 * flow or on the new-flow row only: a step card under the pointer is part of its
 * flow. A step let go anywhere but on its own flow goes back where it was.
 */
const collisions: CollisionDetection = (args) => {
  const id = String(args.active.id);
  const hits = pointerWithin(args);
  if (id.startsWith("preset:") || id.startsWith("saved-flow:")) {
    // For a saved job a card and a slot of a draft are places of their own; a
    // saved flow brings steps of its own and always goes at the end.
    const takesAPlace = id.startsWith("preset:");
    return hits.filter(
      (hit) =>
        hit.id === "new-flow" ||
        String(hit.id).startsWith("flow:") ||
        (takesAPlace && Boolean(hit.data?.droppableContainer?.data?.current?.insertInto)),
    );
  }
  return hits;
};

/** Where the pointer is across the board: a card's left half is before it, its right half after it. */
const pointerX = (event: DragMoveEvent | DragEndEvent) => {
  const start = event.activatorEvent as PointerEvent | null;
  return start && "clientX" in start ? start.clientX + event.delta.x : null;
};

const flowOf = (over: string) => (over.startsWith("flow:") ? over.slice(5) : null);

/** The step number a saved job takes in a flow: its own place only while the flow is edited. */
const placeIn = (flow: Flow, index: number | undefined) =>
  flow.editing && index !== undefined && index < flow.steps.length ? index : undefined;

type Modal =
  | {
      kind: "review";
      flowId: string;
      scope: ReviewScope;
      /** The steps a drop just added: the window's way out takes them off again. */
      added?: string[];
      /** The returned copy opens even if the next list fetch fails. */
      again?: { copy: Flow; source?: string };
    }
  | { kind: "attention"; flowId: string; stepId: string }
  | { kind: "values"; flowId: string; stepId: string }
  | null;

export default function Board() {
  const location = useLocation();
  const navigate = useNavigate();
  const presets = usePresets();
  const savedFlows = useSavedFlows();
  const flows = useFlows();

  const createFlow = useCreateFlow();
  const addStep = useAddStep();
  const patchStep = usePatchStep();
  const removeStep = useRemoveStep();
  const startFlow = useStartFlow();
  const confirmHeld = useConfirmHeld();
  const stopFlow = useStopFlow();
  const resumeFlow = useResumeFlow();
  const renameFlow = useRenameFlow();
  const rerunFlow = useRerunFlow();
  const pinFlow = usePinFlow();
  const setEditing = useSetEditing();
  const duplicateFlow = useDuplicateFlow();
  const clearFlow = useClearFlow();
  const deleteFlow = useDeleteFlow();
  const closeFlow = useCloseFlow();
  const linkBuild = useLinkBuild();
  const saveAsFlow = useSaveAsFlow();
  const savingFlows = useSavingFlows();
  const instantiate = useInstantiateSavedFlow();
  const jenkins = useJenkinsStatus();
  const jenkinsReachable = jenkins.data?.reachable !== false;
  const rail = useRail();

  const [dragging, setDragging] = useState<Preset | null>(null);
  const [draggingStep, setDraggingStep] = useState<{ step: Step; flow: Flow } | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  // The last refusal, and where it is read: above the board, or under the row
  // of the saved flow it was about. Whatever works next clears it, wherever.
  const [problem, setProblem] = useState<{ text: string; row: string | null } | null>(null);
  const refuse = (text: string, row: string | null = null) => setProblem({ text, row });
  // A saved flow that was refused because one of its saved jobs changed in Jenkins.
  const [drifted, setDrifted] = useState<Preset | null>(null);
  const [draggingFlow, setDraggingFlow] = useState<SavedFlow | null>(null);
  // The place a dragged saved job would take: a step number in one flow.
  const [insertAt, setInsertAt] = useState<InsertPlace | null>(null);
  // What the last drop did, in words, for a screen reader.
  const spoken = useRef<string | undefined>(undefined);
  // The list of saved jobs and saved flows: for one flow, or for a new one (null).
  const [picker, setPicker] = useState<{ flowId: string | null; anchor: HTMLElement } | null>(null);
  const newFlowButton = useRef<HTMLSpanElement>(null);
  // Remove, and how to take it back while the line above the board says so.
  const [notice, setNotice] = useState<{ text: string; undo: () => void } | null>(null);
  const noticeTimer = useRef<number | undefined>(undefined);
  // Drafts off the board already; each is deleted once its Undo runs out.
  const [hidden, setHidden] = useState<string[]>([]);
  const pendingDelete = useRef<string | null>(null);
  // The copy Duplicate just made: its name opens for typing.
  const [renameId, setRenameId] = useState<string | null>(null);
  // The flow the board was just opened at, lit for a moment.
  const [highlightId, setHighlightId] = useState<string | null>(null);
  // The saved flow Save just kept, scrolled into view in the column.
  const [savedId, setSavedId] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const visible = visibleFlows(flows.data ?? []).filter((flow) => !hidden.includes(flow.id));
  const presetById = new Map((presets.data ?? []).map((preset) => [preset.id, preset]));
  const savedFlowById = new Map((savedFlows.data ?? []).map((saved) => [saved.id, saved]));
  const openFlow = modal
    ? visible.find((flow) => flow.id === modal.flowId) ?? (modal.kind === "review" ? modal.again?.copy : undefined)
    : undefined;
  const valuesStep =
    modal?.kind === "values" ? openFlow?.steps.find((step) => step.id === modal.stepId) : undefined;
  const attentionStep =
    modal?.kind === "attention" ? openFlow?.steps.find((step) => step.id === modal.stepId) : undefined;
  /** The parameters a step's saved job asks for at launch. */
  const askedOf = (step: Step) =>
    Object.entries(presetById.get(step.preset_id)?.params ?? {})
      .filter(([, setting]) => setting.mode === "ask")
      .map(([name]) => name);
  const presetOf = (step: Step) => presetById.get(step.preset_id);

  /** What an id being dragged is called on screen. */
  const nameOf = (id: string) =>
    id.startsWith("preset:")
      ? (presetById.get(id.slice(7))?.name ?? id)
      : id.startsWith("saved-flow:")
        ? (savedFlowById.get(id.slice(11))?.name ?? id)
        : (visible.flatMap((flow) => flow.steps).find((step) => step.id === id)?.preset_name ?? id);

  const onDragStart = (event: DragStartEvent) => {
    const id = String(event.active.id);
    setPicker(null);
    setDragging(id.startsWith("preset:") ? (presetById.get(id.slice(7)) ?? null) : null);
    setDraggingFlow(id.startsWith("saved-flow:") ? (savedFlowById.get(id.slice(11)) ?? null) : null);
    const flow = visible.find((item) => item.steps.some((step) => step.id === id));
    const step = flow?.steps.find((item) => item.id === id);
    setDraggingStep(flow && step ? { step, flow } : null);
    setInsertAt(null);
  };

  /** Where a dragged saved job would land, from what is under the pointer. */
  const placeOf = (event: DragMoveEvent | DragEndEvent, current: InsertPlace | null) =>
    String(event.active.id).startsWith("preset:")
      ? insertTarget(
          event.collisions,
          current,
          (flowId) => {
            const flow = visible.find((item) => item.id === flowId);
            return flow ? flow.steps.length : null;
          },
          pointerX(event),
        )
      : null;

  const onDragMove = (event: DragMoveEvent) => {
    if (!String(event.active.id).startsWith("preset:")) return;
    setInsertAt((current) => placeOf(event, current));
  };

  // History, Duplicate and New flow open the board at one flow: #flow-<id>. It is
  // scrolled to and lit once, as soon as it is there.
  const flowCount = visible.length;
  const shownFor = useRef<string | null>(null);
  useEffect(() => {
    if (!location.hash.startsWith("#flow-") || shownFor.current === location.key) return;
    const section = document.getElementById(location.hash.slice(1));
    if (!section) return;
    shownFor.current = location.key;
    section.scrollIntoView({ block: "start" });
    setHighlightId(location.hash.slice(6));
    focusFlow(location.hash.slice(6));
  }, [location.hash, location.key, flowCount]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!highlightId) return;
    const timer = window.setTimeout(() => setHighlightId(null), HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [highlightId]);
  const showFlow = (flowId: string) => navigate({ hash: `flow-${flowId}` }, { replace: true });
  // Keyboard focus goes to the flow's first button, unless something in it has it already.
  const focusFlow = (flowId: string) =>
    requestAnimationFrame(() => {
      const section = document.getElementById(`flow-${flowId}`);
      if (!section || section.contains(document.activeElement)) return;
      section.querySelector<HTMLElement>("button:not([disabled])")?.focus({ preventScroll: true });
    });

  // The copy's name opened for typing as it appeared; the next render must not open it again.
  useEffect(() => {
    if (renameId && visible.some((flow) => flow.id === renameId)) setRenameId(null);
  }, [renameId, flowCount]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!savedId) return;
    const row = document.getElementById(savedFlowRowId(savedId));
    if (!row) return;
    row.scrollIntoView({ block: "nearest" });
    setSavedId(null);
  }, [savedId, savedFlows.data]);

  // History already received the copy; opening its review needs no second fetch.
  const runAgain = location.state as RunAgainState | null;
  useEffect(() => {
    if (!runAgain?.review) return;
    setModal({
      kind: "review",
      flowId: runAgain.review.id,
      scope: { kind: "start" },
      again: { copy: runAgain.review, source: runAgain.source },
    });
    navigate(location.pathname + location.hash, { replace: true, state: null });
  }, [runAgain]); // eslint-disable-line react-hooks/exhaustive-deps

  // Leaving the board sends the delete a draft is waiting for.
  useEffect(
    () => () => {
      window.clearTimeout(noticeTimer.current);
      deleteNow();
    },
    [], // eslint-disable-line react-hooks/exhaustive-deps
  );

  /** What a drop does, before it is done: said to a screen reader as it lands. */
  function landingOf(active: string, over: string | null, place: InsertPlace | null): Landing | null {
    if (!over) return null;
    if (active.startsWith("preset:") || active.startsWith("saved-flow:")) {
      if (over === "new-flow") return { kind: "new" };
      const flowId = active.startsWith("preset:") ? (place?.flowId ?? flowOf(over)) : flowOf(over);
      const flow = visible.find((item) => item.id === flowId);
      if (!flow) return null;
      if (active.startsWith("saved-flow:")) return { kind: "flow", flow: flow.name };
      const index = hasEnded(flow) ? undefined : placeIn(flow, place?.index);
      return { kind: "step", step: (index ?? flow.steps.length) + 1, flow: flow.name };
    }
    const flow = visible.find((item) => item.steps.some((step) => step.id === active));
    const target = flow?.steps.find((step) => step.id === over);
    return target && over !== active ? { kind: "moved", step: target.position + 1 } : null;
  }

  const onDragEnd = async (event: DragEndEvent) => {
    setDragging(null);
    setDraggingFlow(null);
    setDraggingStep(null);
    setProblem(null);
    setDrifted(null);
    const place = placeOf(event, insertAt);
    setInsertAt(null);
    const active = String(event.active.id);
    const over = event.over ? String(event.over.id) : null;
    spoken.current = landed(nameOf(active), landingOf(active, over, place));
    // Let go off every flow, a step goes back where it was: only its own button removes it.
    if (!over) return;

    try {
      if (active.startsWith("preset:")) {
        const presetId = active.slice(7);
        const flowId = place?.flowId ?? flowOf(over);
        if (over === "new-flow") await addPreset(presetId, null);
        else if (flowId) await addPreset(presetId, flowId, place?.index);
      } else if (active.startsWith("saved-flow:")) {
        await addSavedFlow(active.slice(11), over === "new-flow" ? null : flowOf(over));
      } else if (over !== active) {
        await movePlannedStep(active, over);
      }
    } catch (error) {
      refuse(error instanceof Error ? error.message : String(error));
    }
  };

  /** A step added to a flow that has started waits, held, until it is reviewed. */
  function reviewAdded(before: Flow, after: Flow) {
    if (before.status === "draft") return;
    const added = after.steps.filter((step) => !before.steps.some((item) => item.id === step.id));
    setModal({
      kind: "review",
      flowId: after.id,
      scope: { kind: "held" },
      added: added.map((step) => step.id),
    });
  }

  /** A saved job added to a flow (at `index`, while it is edited), or as a new flow (null). */
  async function addPreset(presetId: string, flowId: string | null, index?: number) {
    if (flowId === null) {
      const preset = presetById.get(presetId);
      return createFlow.mutateAsync({ name: preset?.name, steps: [{ preset_id: presetId }] });
    }
    const flow = visible.find((item) => item.id === flowId);
    if (flow && hasEnded(flow)) {
      // A card dropped on a flow that ended opens a copy of it to change, in its
      // place; what ran is in History.
      const draft = await rerunFlow.mutateAsync({ flowId, editing: true });
      return addStep.mutateAsync({ flowId: draft.id, step: { preset_id: presetId } });
    }
    const position = flow ? placeIn(flow, index) : undefined;
    const after = await addStep.mutateAsync({ flowId, step: { preset_id: presetId }, position });
    if (flow) reviewAdded(flow, after);
    return after;
  }

  /** A saved flow's steps added to a flow, or as a new flow (null). */
  async function addSavedFlow(savedFlowId: string, flowId: string | null) {
    const onto = flowId ? visible.find((item) => item.id === flowId) : undefined;
    // The same as for one saved job: a flow that ended opens a copy to change.
    const target =
      onto && hasEnded(onto)
        ? (await rerunFlow.mutateAsync({ flowId: onto.id, editing: true })).id
        : (flowId ?? undefined);
    let after: Flow;
    try {
      after = await instantiate.mutateAsync({ id: savedFlowId, flowId: target });
    } catch (error) {
      // The refusal does not say which saved job changed; the saved flow does.
      const steps = savedFlowById.get(savedFlowId)?.steps ?? [];
      const changed = steps
        .map((step) => presetById.get(step.preset_id))
        .find((preset) => preset?.drift);
      if (error instanceof ApiError && error.status === 409 && changed) {
        setDrifted(changed);
        return null;
      }
      throw error;
    }
    if (onto && onto.id === target) reviewAdded(onto, after);
    return after;
  }

  /** A pick from the list does what a drop there would; a new flow is scrolled to. */
  function onPick(picked: Picked, flowId: string | null) {
    setProblem(null);
    setDrifted(null);
    const adding =
      picked.kind === "preset"
        ? addPreset(picked.preset.id, flowId)
        : addSavedFlow(picked.savedFlow.id, flowId);
    adding.then(
      (flow) => {
        if (flowId === null && flow) showFlow(flow.id);
      },
      said.onError,
    );
  }

  /** The drafts removed a moment ago are deleted now, not when their Undo runs out. */
  function deleteNow() {
    const flowId = pendingDelete.current;
    if (!flowId) return;
    pendingDelete.current = null;
    const unhide = () => setHidden((ids) => ids.filter((id) => id !== flowId));
    deleteFlow.mutateAsync({ flowId }).then(unhide, (error: Error) => {
      unhide();
      refuse(error.message);
    });
  }

  /** The line above the board that takes a Remove back, for a few seconds. */
  function offerUndo(text: string, undo: () => void) {
    window.clearTimeout(noticeTimer.current);
    setNotice({ text, undo });
    noticeTimer.current = window.setTimeout(() => {
      deleteNow();
      setNotice(null);
    }, UNDO_MS);
  }

  /** What a refusal says, and what clears the last one away when the next works. */
  const said = {
    onSuccess: () => {
      setProblem(null);
      setDrifted(null);
    },
    onError: (error: Error) => refuse(error.message),
  };

  /** A refusal of something done on the board; one about a saved flow's row is read there. */
  const onBoard = problem && problem.row === null ? problem.text : null;

  // One click, and Undo for a while: a draft goes from the board at once and is
  // deleted when Undo runs out; a flow that ran is taken off and can come back.
  function onDelete(flow: Flow) {
    // The Remove before this one can no longer be taken back.
    window.clearTimeout(noticeTimer.current);
    setNotice(null);
    deleteNow();
    if (trashAction(flow) === "delete") {
      pendingDelete.current = flow.id;
      setHidden((ids) => [...ids, flow.id]);
      offerUndo(`Deleted draft "${flow.name}"`, () => {
        pendingDelete.current = null;
        setHidden((ids) => ids.filter((id) => id !== flow.id));
      });
      return;
    }
    clearFlow.mutate(
      { flowId: flow.id },
      {
        onSuccess: () => {
          said.onSuccess();
          offerUndo(`Removed "${flow.name}" from the board`, () =>
            clearFlow.mutate({ flowId: flow.id, cleared: false }, said),
          );
        },
        onError: said.onError,
      },
    );
  }

  /** Removing the last step of a flow being built removes the flow, as Remove does. */
  async function removePlannedStep(stepId: string) {
    const flow = visible.find((item) => item.steps.some((step) => step.id === stepId));
    if (!flow) return;
    if (flow.editing && flow.steps.length === 1) return onDelete(flow);
    await removeStep.mutateAsync({ flowId: flow.id, stepId });
  }

  async function movePlannedStep(stepId: string, overId: string) {
    const flow = visible.find((item) => item.steps.some((step) => step.id === stepId));
    const target = flow?.steps.find((step) => step.id === overId);
    if (!flow || !target) return;
    await patchStep.mutateAsync({ flowId: flow.id, stepId, patch: { position: target.position } });
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collisions}
      onDragStart={onDragStart}
      onDragMove={onDragMove}
      onDragEnd={onDragEnd}
      onDragCancel={() => {
        setDragging(null);
        setDraggingFlow(null);
        setDraggingStep(null);
        setInsertAt(null);
      }}
      // Only a mouse drags; the keyboard goes through the list and the step details.
      accessibility={{
        screenReaderInstructions: { draggable: "" },
        announcements: boardAnnouncements(nameOf, () => spoken.current),
      }}
    >
      <div
        className={`grid min-h-0 transition-opacity duration-150 ${
          rail.collapsed ? "grid-cols-[48px_minmax(0,1fr)]" : "grid-cols-[264px_minmax(0,1fr)]"
        } ${modal ? "pointer-events-none opacity-[.35]" : ""}`}
      >
        {rail.collapsed ? (
          // Only the button opens it: the label under it is a label.
          <aside
            aria-label="Saved jobs"
            className="flex w-12 flex-col items-center gap-3 border-r border-hairline pt-4"
          >
            <RailToggle open={false} onClick={rail.toggle} />
            <span className="[writing-mode:vertical-rl]">
              <GroupLabel>saved jobs</GroupLabel>
            </span>
          </aside>
        ) : (
          <SavedJobs
            presets={presets.data ?? []}
            savedFlows={savedFlows.data ?? []}
            onCollapse={rail.toggle}
            problem={problem?.row ? { row: problem.row, text: problem.text } : null}
            onProblem={(row, why) => (why ? refuse(why, row) : said.onSuccess())}
          />
        )}

        {/* The skip link lands here; the focus ring stays off the whole column. */}
        <main id="flows" tabIndex={-1} className="flex min-w-0 flex-col overflow-hidden outline-hidden">
          <h1 className="sr-only">Board</h1>
          {(onBoard || drifted || notice) && (
            // Refusals and the Undo line sit above the flows.
            <div className="flex flex-none flex-col gap-1 border-b border-hairline px-5 py-2 text-[14px]">
              {(onBoard || drifted) && (
                <div className="text-warn">
                  {onBoard}
                  {drifted && (
                    <>
                      {onBoard && " "}
                      Jenkins changed{" "}
                      <Link to={`/library/${drifted.id}`} className="text-warn">
                        {drifted.name}
                      </Link>
                      . Review it in Library, then drop the saved flow again.
                    </>
                  )}
                </div>
              )}
              {notice && (
                <div role="status" className="flex items-center gap-2 text-text">
                  <span className="min-w-0 truncate">{notice.text}</span>
                  <span className="text-dim">·</span>
                  <QuietButton
                    onClick={() => {
                      window.clearTimeout(noticeTimer.current);
                      notice.undo();
                      setNotice(null);
                    }}
                  >
                    Undo
                  </QuietButton>
                </div>
              )}
            </div>
          )}
          <div
            className="flex min-w-0 flex-1 flex-col overflow-auto px-5 pb-6 pt-2"
            // The dot grid marks the surface things are dropped onto; nothing else has it.
            style={{
              backgroundImage: "radial-gradient(var(--jk-grid) 1px, transparent 1px)",
              backgroundSize: "22px 22px",
            }}
          >
            <div className="flex items-center gap-3 pb-3.5 pt-2">
              <span className="text-[16px] font-semibold">Flows</span>
              <span ref={newFlowButton} className="inline-flex">
                <IconButton
                  icon={Plus}
                  label="New flow"
                  quiet
                  onClick={() =>
                    setPicker((open) =>
                      open?.flowId === null || !newFlowButton.current
                        ? null
                        : { flowId: null, anchor: newFlowButton.current },
                    )
                  }
                />
              </span>
            </div>

            {visible.length === 0 && <div className="pb-4 text-[14px] text-dim">No flows yet.</div>}

            {visible.map((flow) => (
              <FlowSection
                key={flow.id}
                flow={flow}
                canReview={jenkinsReachable}
                onReview={() => setModal({ kind: "review", flowId: flow.id, scope: { kind: "start" } })}
                onStop={(abort) => stopFlow.mutate({ flowId: flow.id, abort }, said)}
                onResume={(fromPosition) =>
                  setModal({ kind: "review", flowId: flow.id, scope: { kind: "resume", fromPosition } })
                }
                onReviewHeld={() => setModal({ kind: "review", flowId: flow.id, scope: { kind: "held" } })}
                onRename={(name) => renameFlow.mutate({ flowId: flow.id, name }, said)}
                onPin={(pinned) => pinFlow.mutate({ flowId: flow.id, pinned }, said)}
                insertIndex={insertAt?.flowId === flow.id ? insertAt.index : null}
                busy={rerunFlow.isPending || duplicateFlow.isPending || setEditing.isPending}
                onEdit={(editing) => {
                  // A flow that ended is a record: it is not reopened, a copy of it is.
                  if (hasEnded(flow)) rerunFlow.mutate({ flowId: flow.id, editing: true }, said);
                  else setEditing.mutate({ flowId: flow.id, editing }, said);
                }}
                onDuplicate={() =>
                  duplicateFlow.mutate(
                    { flowId: flow.id },
                    {
                      // The copy is scrolled to with its name open: Enter keeps "… copy".
                      onSuccess: (copy) => {
                        said.onSuccess();
                        setRenameId(copy.id);
                        showFlow(copy.id);
                      },
                      onError: said.onError,
                    },
                  )
                }
                onRunAgain={() =>
                  // The copy goes straight to its review: run again is one decision,
                  // and Cancel there only removes the new copy.
                  rerunFlow.mutate(
                    { flowId: flow.id },
                    {
                      onSuccess: (again) => {
                        said.onSuccess();
                        setModal({
                          kind: "review",
                          flowId: again.id,
                          scope: { kind: "start" },
                          again: { copy: again, source: flow.id },
                        });
                      },
                      onError: said.onError,
                    },
                  )
                }
                keptAs={flow.saved_flow_id ? (savedFlowById.get(flow.saved_flow_id) ?? null) : null}
                saving={savingFlows.includes(flow.id)}
                onSaveAsFlow={() =>
                  // The promise, not per-call callbacks: those run only for the
                  // latest call, so a second flow saved at once would lose a refusal.
                  saveAsFlow.mutateAsync(flow.id).then(
                    (kept) => {
                      said.onSuccess();
                      setSavedId(kept.saved_flow_id);
                    },
                    said.onError,
                  )
                }
                onDelete={() => onDelete(flow)}
                onOpenAttention={(step) => openAttention(flow, step)}
                onCondition={(step, condition) =>
                  patchStep.mutate({ flowId: flow.id, stepId: step.id, patch: { condition } }, said)
                }
                askedOf={askedOf}
                presetOf={presetOf}
                onFillValues={(step) => setModal({ kind: "values", flowId: flow.id, stepId: step.id })}
                onRemoveStep={(step) =>
                  removePlannedStep(step.id).then(said.onSuccess, said.onError)
                }
                onMoveStep={(step, position) =>
                  patchStep.mutate(
                    { flowId: flow.id, stepId: step.id, patch: { position } },
                    {
                      ...said,
                      // Focus follows the card to its new place.
                      onSuccess: () => {
                        said.onSuccess();
                        requestAnimationFrame(() =>
                          document.querySelector<HTMLElement>(`[data-step-id="${step.id}"]`)?.focus(),
                        );
                      },
                    },
                  )
                }
                onAddStep={(tile) =>
                  setPicker((open) => (open?.anchor === tile ? null : { flowId: flow.id, anchor: tile }))
                }
                startRenaming={flow.id === renameId}
                highlight={flow.id === highlightId}
              />
            ))}

            <NewFlowRow />
          </div>
        </main>
      </div>

      {picker && (
        <JobPicker
          // Opened from another "+", it is placed anew against that one.
          key={picker.flowId ?? "new"}
          anchor={picker.anchor}
          label={picker.flowId === null ? "New flow" : "Add step"}
          presets={presets.data ?? []}
          savedFlows={savedFlows.data ?? []}
          onPick={(picked) => onPick(picked, picker.flowId)}
          onClose={() => setPicker(null)}
        />
      )}

      <DragOverlay dropAnimation={null}>
        {dragging && (
          <div
            className={`${CARD_CLASS} flex flex-col gap-[5px] rounded-md border border-accent bg-surface px-3 py-[9px] shadow-[0_8px_24px_rgba(0,0,0,.5)]`}
          >
            <PresetCardBody preset={dragging} />
          </div>
        )}
        {draggingFlow && (
          <div className="flex w-[274px] items-center justify-between gap-2 rounded-md border border-accent bg-surface px-3 py-2 shadow-[0_8px_24px_rgba(0,0,0,.5)]">
            <span className="inline-flex min-w-0 items-center gap-2">
              <Bookmark size={14} aria-hidden className="flex-none text-dim" />
              <span className="overflow-hidden text-ellipsis whitespace-nowrap">
                {draggingFlow.name}
              </span>
            </span>
            <span className="whitespace-nowrap font-mono text-[13px] text-dim">
              {draggingFlow.steps.length} {draggingFlow.steps.length === 1 ? "step" : "steps"}
            </span>
          </div>
        )}
        {/* With an overlay mounted the dragged card itself stays put, so a step
            needs a ghost of its own to follow the pointer. */}
        {draggingStep && (
          <div
            className={`${CARD_CLASS} flex flex-col gap-[7px] rounded-md border border-accent bg-surface px-3 py-2.5 shadow-[0_8px_24px_rgba(0,0,0,.5)]`}
          >
            <StepCardBody
              step={draggingStep.step}
              flow={draggingStep.flow}
              asked={askedOf(draggingStep.step)}
              preset={presetOf(draggingStep.step)}
            />
          </div>
        )}
      </DragOverlay>

      {modal?.kind === "review" && openFlow && (
        <ReviewRun
          flow={openFlow}
          scope={modal.scope}
          onClose={async () => {
            if (modal.again) await deleteFlow.mutateAsync({ flowId: openFlow.id });
            setModal(null);
          }}
          onDiscard={
            modal.added
              ? () => {
                  const flowId = openFlow.id;
                  // Last first, one at a time: a step's id is its position, and each
                  // removal renumbers the steps after it.
                  const added = [...(modal.added ?? [])].reverse();
                  added
                    .reduce<Promise<unknown>>(
                      (done, stepId) => done.then(() => removeStep.mutateAsync({ flowId, stepId })),
                      Promise.resolve(),
                    )
                    .then(said.onSuccess, said.onError);
                }
              : undefined
          }
          onRun={(runValues, token) => {
            const flowId = openFlow.id;
            const scope = modal.scope;
            const source = modal.again?.source;
            setModal(null);
            // The button that opened the review is gone once the flow runs.
            const ran = {
              ...said,
              onSuccess: () => {
                said.onSuccess();
                focusFlow(flowId);
                // Cleanup is independent of the successful start; never report it as a failed launch.
                if (source) clearFlow.mutate({ flowId: source }, {
                  onError: () => refuse("The new flow started. The previous run is still on the board; remove it when ready."),
                });
              },
            };
            if (scope.kind === "held") confirmHeld.mutate({ flowId, runValues, token }, ran);
            else if (scope.kind === "resume")
              resumeFlow.mutate({ flowId, fromPosition: scope.fromPosition, runValues, token }, ran);
            else startFlow.mutate({ flowId, runValues, token }, ran);
          }}
        />
      )}

      {modal?.kind === "values" && openFlow && valuesStep && (
        <RunValues
          step={valuesStep}
          asked={askedOf(valuesStep)}
          definitions={presetById.get(valuesStep.preset_id)?.definitions ?? []}
          stepCount={openFlow.steps.length}
          carried={carriedValues(openFlow.steps, valuesStep.position)}
          onClose={() => setModal(null)}
          onSave={(values) => {
            const stepId = valuesStep.id;
            // A refusal is the window's to show; this only closes it once kept.
            return patchStep
              .mutateAsync({
                flowId: openFlow.id,
                stepId,
                patch: { run_values: { ...valuesStep.run_values, ...values } },
              })
              .then(() => {
                said.onSuccess();
                // Only this step's window: another may have been opened meanwhile.
                setModal((open) => (open?.kind === "values" && open.stepId === stepId ? null : open));
              });
          }}
        />
      )}

      {attentionStep && openFlow && (
        <NeedsAttention
          flow={openFlow}
          step={attentionStep}
          onClose={() => setModal(null)}
          onLink={(buildNumber) => {
            setModal(null);
            linkBuild.mutate({ flowId: openFlow.id, stepId: attentionStep.id, buildNumber }, said);
          }}
          onCloseRun={(buildNumbers) => {
            setModal(null);
            closeFlow.mutate({ flowId: openFlow.id, buildNumbers }, said);
          }}
        />
      )}
    </DndContext>
  );

  function openAttention(flow: Flow, step?: Step) {
    const flagged = step ?? flow.steps.find((item) => item.state === "needs_attention");
    if (flagged) setModal({ kind: "attention", flowId: flow.id, stepId: flagged.id });
  }
}
