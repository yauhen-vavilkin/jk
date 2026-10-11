// Everything about one step that the card has no room for: the values, the
// times, the links, and for a step that waits, where else it can go.
import { ExternalLink } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { Preset, Step } from "@/api/types";
import Menu from "@/components/ui/Menu";
import { stepValues } from "@/lib/cardValues";
import { clockWithSeconds } from "@/lib/time";

const WIDTH = 430;

export default function StepPopover({
  step,
  onClose,
  anchor,
  preset,
  asked,
  moveTo = [],
  onMove,
  readOnly = false,
}: {
  step: Step;
  onClose: () => void;
  /** The card it opened from: it opens where it fits, and a second press there closes it. */
  anchor?: HTMLElement | null;
  /** The step's saved job, so a step not sent yet lists everything it will send. */
  preset?: Preset;
  /** The parameters its saved job asks for at launch. */
  asked?: string[];
  /** The positions this step can move to, one either side. */
  moveTo?: number[];
  onMove?: (position: number) => void;
  /** History describes the recorded run without editor actions. */
  readOnly?: boolean;
}) {
  // Placed once, when it opens: above a card low in the window, and to the left
  // of the last card of a row, so its links are never under the window's edge.
  const [place] = useState(() => {
    const box = anchor?.getBoundingClientRect();
    return {
      side: box && box.bottom > window.innerHeight * 0.55 ? "above" : "below",
      align: box && box.left + WIDTH > window.innerWidth ? "right" : "left",
    } as const;
  });
  const opener = useRef<HTMLElement | null>(anchor ?? null);
  const sent = stepValues(step, preset, asked);
  const link = "inline-flex items-center gap-1.5";

  return (
    <Menu
      onClose={onClose}
      align={place.align}
      side={place.side}
      width={WIDTH}
      anchor={opener}
      role="dialog"
      label={`Step ${step.position + 1} details`}
    >
      <div className="flex flex-col gap-2.5 px-3 py-2.5">
        <div className="max-h-56 overflow-auto font-mono text-[13px] leading-[1.7]">
          {sent.map((item) => (
            <div key={item.name} className="flex gap-2.5">
              <span className="w-[160px] flex-none text-dim">{item.name}</span>
              {/* A value typed at launch is accent, as everywhere. */}
              <span className={`break-all ${item.asked ? "text-accent" : ""}`}>
                {item.value || <span className={item.asked ? "" : "text-dim"}>empty</span>}
              </span>
            </div>
          ))}
          {sent.length === 0 && <span className="text-dim">Nothing yet.</span>}
        </div>

        {(step.sent_at || step.started_at || step.finished_at || step.note) && (
          <div className="font-mono text-[13px] text-dim">
            {step.sent_at && <div>Sent {clockWithSeconds(step.sent_at)}</div>}
            {step.started_at && <div>Started {clockWithSeconds(step.started_at)}</div>}
            {step.finished_at && <div>Finished {clockWithSeconds(step.finished_at)}</div>}
            {step.note && <div className="text-key">{step.note}</div>}
          </div>
        )}

        <div className="flex flex-wrap gap-x-[18px] gap-y-1 text-[14px]">
          <a href={step.job_url} target="_blank" rel="noreferrer" className={link}>
            Job in Jenkins <ExternalLink size={13} aria-hidden />
          </a>
          {!readOnly && <Link to={`/library/${step.preset_id}`}>Edit saved job</Link>}
        </div>

        {onMove && moveTo.length > 0 && (
          <div className="flex flex-wrap gap-x-[18px] gap-y-1 text-[14px]">
            {moveTo.map((position) => (
              <button
                key={position}
                type="button"
                onClick={() => {
                  onClose();
                  onMove(position);
                }}
                className="text-key transition-colors duration-150 hover:text-text"
              >
                Move to step {position + 1}
              </button>
            ))}
          </div>
        )}
      </div>
    </Menu>
  );
}
