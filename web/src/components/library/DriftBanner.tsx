// Jenkins changed the job this saved job depends on. Until a human has looked,
// the saved job does not run; this is both the break and the one-click heal,
// which stores the new parameters as their rows below are set.
import type { Preset } from "@/api/types";
import { SecondaryButton } from "@/components/ui/primitives";
import StatusIcon from "@/components/ui/StatusIcon";

export const ACCEPT_LABEL = "Accept as shown";

function changedOn(seenAt: string): string {
  return new Date(seenAt).toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function DriftBanner({
  preset,
  onAccept,
  busy,
}: {
  preset: Preset;
  onAccept: () => void;
  busy: boolean;
}) {
  const drift = preset.drift;
  if (!drift) return null;

  const jobName = preset.job_path.split("/").pop() ?? preset.job_path;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-warn px-4 py-3">
      <div className="flex items-baseline gap-2.5">
        <StatusIcon name="alert" className="text-warn" />
        <p>
          <span className="font-medium">Jenkins changed {jobName} on {changedOn(drift.seen_at)}.</span>{" "}
          <span className="text-[14px] text-dim">JK will not run this saved job until you review the change.</span>
        </p>
      </div>

      <div className="flex flex-wrap gap-x-7 pl-[22px] font-mono text-[13px] leading-[1.6]">
        {drift.added.map((item) => (
          <span key={`+${item.name}`}>
            <span className="text-ok">+ {item.name}</span> <span className="text-dim">default</span>{" "}
            {item.default ?? "—"}
          </span>
        ))}
        {drift.removed.map((item) => (
          <span key={`-${item.name}`}>
            <span className="text-warn">− {item.name}</span>{" "}
            <span className="text-dim">you had</span> {item.had ?? "empty"}
          </span>
        ))}
        {drift.changed.map((item) => (
          <span key={`~${item.name}`}>
            <span className="text-warn">{item.name}</span>{" "}
            <span className="text-dim">{item.reason}</span>
          </span>
        ))}
      </div>

      <div className="flex items-center gap-4 pl-[22px] text-[14px]">
        <SecondaryButton onClick={onAccept} disabled={busy}>
          {ACCEPT_LABEL}
        </SecondaryButton>
      </div>
    </div>
  );
}
