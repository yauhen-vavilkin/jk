// The end of a flow's row: a narrow "+" that opens the saved-job picker. While a
// saved job is dragged over the flow it widens to a card and becomes the drop
// indicator, and in a draft a slot also stands open between two cards, in the
// place the card would take.
import { useDroppable } from "@dnd-kit/core";
import { Plus } from "lucide-react";

import { CARD_CLASS } from "./cardMetrics";

export default function AddSlot({
  flowId,
  position,
  over,
  kind = "add",
  insertable = false,
  onAdd,
}: {
  flowId: string;
  position: number;
  over: boolean;
  /** `add` closes the row; `slot` stands open between two cards. */
  kind?: "add" | "slot";
  /** Only a draft takes a step in a place of its own. */
  insertable?: boolean;
  /** Opens the picker of saved jobs and saved flows, under the tile it is given. */
  onAdd?: (tile: HTMLElement) => void;
}) {
  const droppable = useDroppable({
    id: `${kind}:${flowId}`,
    data: insertable ? { insertInto: flowId, index: position } : undefined,
  });
  const frame = "flex items-center justify-center gap-2 rounded-md border border-dashed transition-colors duration-150";

  if (over) {
    return (
      <div
        ref={droppable.setNodeRef}
        className={`${CARD_CLASS} ${frame} border-accent bg-accent-well p-3 text-center text-[14px] leading-[1.4] text-accent`}
      >
        Release to add step {position + 1}
      </div>
    );
  }

  // A flow with no step yet has room for a whole card.
  const size = position === 0 ? CARD_CLASS : "h-[164px] w-12 flex-none";
  const tile = `${size} ${frame} border-hairline text-dim`;
  return onAdd ? (
    <button
      ref={droppable.setNodeRef}
      type="button"
      title="Add step"
      aria-label="Add step"
      onClick={(event) => onAdd(event.currentTarget)}
      className={`${tile} hover:border-dim hover:text-text`}
    >
      <Plus size={14} aria-hidden />
    </button>
  ) : (
    <div ref={droppable.setNodeRef} className={tile}>
      <Plus size={14} aria-hidden />
    </div>
  );
}
