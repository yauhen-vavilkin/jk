// A saved job Jenkins changed, on a saved-job card or a step card: the way to its
// review in Library, in this tab, so no external-link mark.
import { Link } from "react-router-dom";

export function DriftLink({ presetId, title }: { presetId: string; title?: string }) {
  return (
    <Link
      to={`/library/${presetId}`}
      title={title}
      // The card around it opens its own details on a click; this one only leaves.
      onClick={(event) => event.stopPropagation()}
      className="self-start text-[14px] text-warn underline underline-offset-2"
    >
      Jenkins changed it · review
    </Link>
  );
}
