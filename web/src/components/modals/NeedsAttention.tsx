// JK does not know whether Jenkins accepted the request. There is no retry
// control here and no code path to one: the candidates are read-only, and a
// human links one or ends the flow.
import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";

import type { Attention, AttentionCandidate, Flow, Step } from "@/api/types";
import { useAttention } from "@/api/queries";
import InlineConfirm from "@/components/ui/InlineConfirm";
import { SecondaryButton, QuietButton } from "@/components/ui/primitives";
import { clockWithSeconds } from "@/lib/time";
import Modal from "./Modal";
import StatusIcon from "@/components/ui/StatusIcon";

const END_FLOW = "End flow";

/** The question before ending: a matching build still running is named. */
export function endQuestion(candidates: AttentionCandidate[]): string {
  const running = candidates.find((candidate) => candidate.state === "RUNNING");
  return running
    ? `End flow? #${running.number} may still be running.`
    : "End flow? Nothing is sent.";
}

export default function NeedsAttention({
  flow,
  step,
  onClose,
  onLink,
  onCloseRun,
}: {
  flow: Flow;
  step: Step;
  onClose: () => void;
  onLink: (buildNumber: number) => void;
  /** Ends the flow; the builds the window listed go on record with it. */
  onCloseRun: (buildNumbers: number[]) => void;
}) {
  const attention = useAttention(flow.id, step.id);
  const [selected, setSelected] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const candidates = attention.data?.candidates ?? [];

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (candidates.length === 0) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelected((index) => Math.min(candidates.length - 1, index + 1));
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((index) => Math.max(0, index - 1));
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [candidates.length]);

  const chosen = candidates[selected];

  return (
    <Modal width={762} top={60} onClose={onClose} label="Needs attention">
      <div className="flex flex-col gap-1.5 px-7 pb-[18px] pt-[22px]">
        <div className="flex items-baseline gap-3.5">
          <StatusIcon name="alert" size={20} className="text-warn" />
          <span className="text-[20px] font-semibold">Needs attention</span>
          <span className="text-key">
            {flow.name} · step {step.position + 1} of {flow.steps.length}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-3.5 px-7 pb-[18px]">
        <div className="leading-[1.55]">
          <NamedReason reason={attention.data?.reason ?? ""} name={step.preset_name} />{" "}
          {attention.data?.never_again_text}
        </div>
        <Facts attention={attention.data} />
      </div>

      <div className="flex flex-col gap-2.5 overflow-auto border-t border-hairline px-7 py-[18px]">
        <div className="font-mono text-[12px] uppercase tracking-[.06em] text-dim">
          matching builds
        </div>

        {attention.isPending ? (
          <span className="text-[14px] text-dim">Looking for builds…</span>
        ) : attention.isError ? (
          <span className="text-[14px]">Could not look up builds.</span>
        ) : candidates.length === 0 ? (
          <span className="text-[14px]">
            {attention.data?.lookup_error ?? "No build matches what JK sent."}
          </span>
        ) : (
          <>
            <div
              className="flex flex-col gap-1 font-mono text-[13px]"
              role="listbox"
              aria-label="Matching builds"
            >
              {candidates.map((candidate, index) => (
                // Picked by a click or the arrow keys; the build's own link is
                // the row's one Tab stop, and a link cannot sit in a button.
                <div
                  key={candidate.number}
                  role="option"
                  aria-selected={index === selected}
                  onClick={() => setSelected(index)}
                  className={`grid cursor-pointer grid-cols-[88px_76px_84px_minmax(0,1fr)] items-baseline gap-3 rounded-md border px-3 py-2 ${
                    index === selected
                      ? "border-accent bg-accent-well"
                      : "border-transparent hover:bg-surface"
                  }`}
                >
                  <a
                    href={candidate.url}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`Open build #${candidate.number} in Jenkins`}
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex items-center gap-1.5"
                  >
                    #{candidate.number} <ExternalLink size={13} aria-hidden />
                  </a>
                  <span className="text-dim">{candidate.time}</span>
                  <span className={stateClass(candidate.state)}>{candidate.state}</span>
                  <span className="text-key [overflow-wrap:anywhere]">{candidate.detail}</span>
                </div>
              ))}
            </div>
            {attention.data?.agreement_text && (
              <div className="text-[14px] leading-[1.55] text-key">
                {attention.data.agreement_text}
              </div>
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-5 border-t border-hairline px-7 pb-[22px] pt-4">
        <span className="max-w-[340px] text-[14px] leading-[1.5] text-dim">
          {candidates.length > 0
            ? "None yours? Check Jenkins before running again."
            : "Check Jenkins before running again."}
        </span>
        <div className="flex-1" />
        {confirming ? (
          <InlineConfirm
            question={endQuestion(candidates)}
            confirmLabel={END_FLOW}
            cancelLabel="Keep"
            onConfirm={() => onCloseRun(candidates.map((candidate) => candidate.number))}
            onCancel={() => setConfirming(false)}
          />
        ) : (
          // Not before the builds are known: the question names one still running.
          <QuietButton onClick={() => setConfirming(true)} disabled={attention.isPending}>
            {END_FLOW}
          </QuietButton>
        )}
        {chosen && !confirming && (
          <SecondaryButton onClick={() => onLink(chosen.number)}>
            Link #{chosen.number}{flow.status === "stopped" ? "" : " and resume"}
          </SecondaryButton>
        )}
      </div>
    </Modal>
  );
}

function Facts({ attention }: { attention: Attention | undefined }) {
  if (!attention) return null;
  const rows: [string, string][] = [["Job", attention.job_path]];
  if (attention.sent_at) rows.push(["Sent", clockWithSeconds(attention.sent_at)]);
  // A build number JK never learned is left out, never printed as nothing.
  if (attention.next_build_number !== null) {
    rows.push(["Expected build", String(attention.next_build_number)]);
  }
  return (
    <div className="font-mono text-[13px] leading-[1.8] text-text">
      {rows.map(([label, value]) => (
        <div key={label} className="flex gap-2.5">
          <span className="w-[150px] flex-none text-dim">{label}</span>
          <span className="break-all">{value}</span>
        </div>
      ))}
    </div>
  );
}

function stateClass(state: string): string {
  if (state === "RUNNING") return "text-info";
  if (state === "SUCCESS") return "text-ok";
  return "text-warn";
}

/** The saved job's name stands out in the reason. */
function NamedReason({ reason, name }: { reason: string; name: string }) {
  const at = name ? reason.indexOf(name) : -1;
  if (at === -1) return <>{reason}</>;
  return (
    <>
      {reason.slice(0, at)}
      <span className="font-medium">{name}</span>
      {reason.slice(at + name.length)}
    </>
  );
}
