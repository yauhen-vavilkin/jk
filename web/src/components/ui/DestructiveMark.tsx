// The word written beside a destructive job, wherever the panel marks one.
// The triangle stays for problems: needs attention, failure, a Jenkins change.
export const DESTRUCTIVE_TITLE = "Destructive — deletes or recreates the namespace";

export function DestructiveMark({ className = "" }: { className?: string }) {
  return (
    <span className={"font-mono text-[13px] text-warn " + className} title={DESTRUCTIVE_TITLE}>
      destructive
    </span>
  );
}
