// The last row of the board: a hairline and one sentence. Dropping a saved job
// here starts a draft named after it.
import { useDndContext, useDroppable } from "@dnd-kit/core";

export default function NewFlowRow() {
  const droppable = useDroppable({ id: "new-flow" });
  // While something that can start a flow is dragged the row is a target the
  // size of a card: the pointer has to be inside it, so a thin line is not enough.
  const { active } = useDndContext();
  const aimedAt = /^(preset|saved-flow):/.test(String(active?.id ?? ""));
  return (
    <div
      ref={droppable.setNodeRef}
      className={`border-t pt-3.5 text-[14px] transition-colors duration-150 ${
        aimedAt ? "min-h-[164px]" : ""
      } ${
        droppable.isOver ? "border-accent text-accent" : "border-hairline text-dim"
      }`}
    >
      {droppable.isOver ? "Release to start a new flow" : "Drop here to start a new flow"}
    </div>
  );
}
