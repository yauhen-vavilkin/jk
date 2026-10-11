// What every Save in the panel says: `Save` while there is something to keep,
// `Saving…` on its way, and `Saved` once there is nothing left to save.
import { Check } from "lucide-react";

export const SAVE = "Save";
export const SAVING = "Saving…";
export const SAVED = "Saved";
export const NOTHING_TO_SAVE = "Nothing to save";

type SaveButtonState = "unsaved" | "saving" | "saved";

/**
 * The Save of a form. `saved` is drawn off but readable -- the secondary shape,
 * with a check -- because it answers the question of whether the press worked.
 *
 * One button through all three words, off by `aria-disabled` and never by
 * `disabled`: a pressed Save keeps the focus through `Saving…` and `Saved`.
 * The shapes are those of the primary and secondary buttons in primitives.
 */
export default function SaveButton({
  state,
  disabled = false,
  title,
  onClick,
  submit = false,
  steady = false,
}: {
  state: SaveButtonState;
  /** Off for a reason of its own, which `title` gives. */
  disabled?: boolean;
  title?: string;
  onClick?: () => void;
  /** Submits its form, so Enter in a field saves: the form's submit saves, and checks it is on. */
  submit?: boolean;
  /** One width for every word, so what stands to its left stays put. */
  steady?: boolean;
}) {
  const saved = state === "saved";
  const off = disabled || state !== "unsaved";
  return (
    <span className={`inline-flex flex-none justify-end ${steady ? "min-w-[96px]" : ""}`}>
      <button
        type={submit ? "submit" : "button"}
        aria-disabled={off}
        title={saved ? (title ?? NOTHING_TO_SAVE) : state === "saving" ? SAVING : title}
        onClick={off ? undefined : onClick}
        className={`inline-flex h-8 flex-none items-center justify-center whitespace-nowrap rounded-md transition-colors duration-150 ${
          saved
            ? "border border-border px-[14px] text-dim"
            : `px-4 font-semibold ${off ? "bg-border text-dim" : "bg-accent text-on-accent"}`
        }`}
      >
        {saved ? (
          <span className="inline-flex items-center gap-1.5">
            <Check size={16} aria-hidden />
            {SAVED}
          </span>
        ) : state === "saving" ? (
          SAVING
        ) : (
          SAVE
        )}
      </button>
    </span>
  );
}
