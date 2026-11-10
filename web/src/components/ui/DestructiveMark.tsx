// The word written beside a destructive job, wherever the panel marks one.
// On a card it is a quiet fact; in the review window, just before the jobs are
// sent, it is the warning.
export const DESTRUCTIVE_TITLE = "Destructive — deletes or recreates the namespace";

export function DestructiveMark({
  className = "",
  tone = "text-warn",
}: {
  className?: string;
  tone?: "text-warn" | "text-dim";
}) {
  return (
    <span className={`font-mono text-[13px] ${tone} ${className}`} title={DESTRUCTIVE_TITLE}>
      destructive
    </span>
  );
}
