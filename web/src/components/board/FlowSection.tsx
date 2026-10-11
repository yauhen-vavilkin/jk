// One flow: a hairline, a header, and its cards in the order they run.
import { useDndContext, useDroppable } from "@dnd-kit/core";
import { SortableContext, rectSortingStrategy } from "@dnd-kit/sortable";
import { Fragment, useState } from "react";

import type { Condition, Flow, Preset, SavedFlow, Step } from "@/api/types";
import { acceptsAStep, canChangeSteps, hasEnded } from "@/lib/flowState";
import AddSlot from "./AddSlot";
import FlowHeader from "./FlowHeader";
import { firstUnfilled, unfilledOf } from "./headerState";
import StepCard from "./StepCard";
import StepPopover from "./StepPopover";

/** Where a waiting step can go without a mouse: one place either way, among steps that wait too. */
function movesOf(flow: Flow, step: Step): number[] {
  if (step.state !== "planned" || !canChangeSteps(flow)) return [];
  // Steps are renumbered from the lower of the two places on, so all of those must still wait.
  const waitFrom = (low: number) =>
    flow.steps.every((item) => item.position < low || item.state === "planned");
  return [step.position - 1, step.position + 1].filter(
    (target) => target >= 0 && target < flow.steps.length && waitFrom(Math.min(step.position, target)),
  );
}

export default function FlowSection({
  flow,
  canReview,
  onReview,
  onStop,
  onResume,
  onRename,
  onSaveAsFlow,
  onDelete,
  onOpenAttention,
  onCondition,
  onRemoveStep,
  onFillValues,
  askedOf,
  onReviewHeld,
  onRunAgain,
  onEdit,
  onDuplicate,
  onPin,
  busy,
  keptAs,
  saving,
  insertIndex,
  presetOf,
  onMoveStep,
  onAddStep,
  startRenaming,
  highlight = false,
}: {
  flow: Flow;
  canReview: boolean;
  onReview: () => void;
  onStop: (abort: boolean) => void;
  onResume: (fromPosition?: number) => void;
  onRename: (name: string) => void;
  onSaveAsFlow: () => void;
  onDelete: () => void;
  onOpenAttention: (step?: Step) => void;
  onCondition: (step: Step, condition: Condition) => void;
  onRemoveStep: (step: Step) => void;
  /** Opens the window where a draft step's asked values are typed. */
  onFillValues: (step: Step) => void;
  /** The parameters a step's saved job asks for at launch. */
  askedOf: (step: Step) => string[];
  onReviewHeld: () => void;
  onRunAgain: () => void;
  /** Turns editing on or off; on a flow that ended, opens a copy to change. */
  onEdit: (editing: boolean) => void;
  /** A second flow with the same steps, under a free name. */
  onDuplicate: () => void;
  onPin: (pinned: boolean) => void;
  /** A copy is being made; the buttons that make one wait for it. */
  busy: boolean;
  /** The saved flow this one is kept as, if it still exists. */
  keptAs: SavedFlow | null;
  /** Its Save is on its way. */
  saving: boolean;
  /** The step number a dragged saved job would take here, or null. */
  insertIndex: number | null;
  /** A step's saved job: what the step sends, and whether Jenkins changed it. */
  presetOf?: (step: Step) => Preset | undefined;
  /** Moves a waiting step to another place, from its details. */
  onMoveStep?: (step: Step, position: number) => void;
  /** Opens the saved-job picker under the "+" at the end of the row. */
  onAddStep?: (tile: HTMLElement) => void;
  /** Opens the name for typing, as for a copy just made. */
  startRenaming?: boolean;
  /** Lit for a moment: the board was just opened at it. */
  highlight?: boolean;
}) {
  const accepts = acceptsAStep(flow);
  // A card dropped on a flow that ended opens a copy of it to change, so that
  // flow is a target too. A draft nobody is editing is not: it is built already.
  const droppable = useDroppable({ id: `flow:${flow.id}`, disabled: !accepts && !hasEnded(flow) });
  const [openStep, setOpenStep] = useState<{ id: string; card: HTMLElement } | null>(null);
  // Only a saved job or a saved flow adds a step; a card of this flow being
  // moved across it must not light the slot up.
  const { active } = useDndContext();
  const adding = droppable.isOver && /^(preset|saved-flow):/.test(String(active?.id ?? ""));
  const nextToFill = flow.status === "draft" ? firstUnfilled(flow, askedOf) : undefined;

  return (
    <div
      ref={droppable.setNodeRef}
      id={`flow-${flow.id}`}
      // The dashed rule down the left says this flow is open to change. It is a
      // hairline like every other, and only the left side is dashed: the top
      // border is the divider between flows and stays solid.
      className={`flex scroll-mt-4 flex-col border-l border-t border-t-hairline pb-[22px] pl-3 pt-[18px] transition-colors duration-700 ${
        flow.editing ? "border-l-dim [border-left-style:dashed]" : "border-l-transparent"
      } ${highlight ? "bg-surface" : ""}`}
    >
      <FlowHeader
        flow={flow}
        canReview={canReview}
        onReview={onReview}
        onStop={onStop}
        onResume={onResume}
        onRename={onRename}
        onSaveAsFlow={onSaveAsFlow}
        onDelete={onDelete}
        onOpenAttention={() => onOpenAttention()}
        onReviewHeld={onReviewHeld}
        onRunAgain={onRunAgain}
        onEdit={onEdit}
        onDuplicate={onDuplicate}
        onPin={onPin}
        busy={busy}
        keptAs={keptAs}
        saving={saving}
        unfilled={flow.status === "draft" ? unfilledOf(flow, askedOf) : 0}
        nextToFill={nextToFill?.position}
        onFillNext={() => nextToFill && onFillValues(nextToFill)}
        driftOf={(step) => presetOf?.(step)?.drift ?? null}
        startRenaming={startRenaming}
      />

      <SortableContext items={flow.steps.map((step) => step.id)} strategy={rectSortingStrategy}>
        <div className="flex flex-wrap items-start gap-3" role="list">
          {flow.steps.map((step) => (
            <Fragment key={step.id}>
              {insertIndex === step.position && (
                <AddSlot kind="slot" flowId={flow.id} position={step.position} over insertable />
              )}
              <div className="relative flex">
                <StepCard
                  step={step}
                  displayPosition={step.position + (insertIndex !== null && step.position >= insertIndex ? 1 : 0)}
                  flow={flow}
                  onCondition={(condition) => onCondition(step, condition)}
                  onRemove={() => onRemoveStep(step)}
                  asked={askedOf(step)}
                  preset={presetOf?.(step)}
                  onFillValues={() => onFillValues(step)}
                  onOpen={(clicked, card) =>
                    clicked.state === "needs_attention"
                      ? onOpenAttention(clicked)
                      : clicked.held && !flow.editing
                        ? onReviewHeld()
                        : setOpenStep((open) => (open?.id === clicked.id ? null : { id: clicked.id, card }))
                  }
                />
                {openStep?.id === step.id && (
                  <StepPopover
                    step={step}
                    onClose={() => setOpenStep(null)}
                    anchor={openStep.card}
                    preset={presetOf?.(step)}
                    asked={askedOf(step)}
                    moveTo={movesOf(flow, step)}
                    onMove={onMoveStep && ((position) => onMoveStep(step, position))}
                  />
                )}
              </div>
            </Fragment>
          ))}

          {/* A flow that ended shows the slot only while a card is held over it:
              that drop is what opens it for editing again. */}
          {(accepts || adding) && (
            <AddSlot
              flowId={flow.id}
              position={flow.steps.length}
              // Only the one slot the card would land in is lit.
              over={insertIndex === null ? adding : insertIndex === flow.steps.length}
              insertable={flow.editing}
              onAdd={onAddStep}
            />
          )}
        </div>
      </SortableContext>
    </div>
  );
}
