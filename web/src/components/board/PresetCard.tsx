// A saved job, as it sits in the left column. Dragging it onto a flow adds a
// step; a saved job Jenkins has changed under cannot be dragged at all.
import { useDndContext, useDraggable } from "@dnd-kit/core";
import { ExternalLink } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { Preset } from "@/api/types";
import CardValuesBlock from "@/components/ui/CardValuesBlock";
import { DestructiveMark } from "@/components/ui/DestructiveMark";
import Menu from "@/components/ui/Menu";
import { presetCardValues } from "@/lib/cardValues";
import { DriftLink } from "./DriftLink";

/** Why the card cannot be dragged, for the hover title of its drift link. */
function driftNote(preset: Preset): string | null {
  if (!preset.drift) return null;
  const added = preset.drift.added.length;
  const removed = preset.drift.removed.length + preset.drift.changed.length;
  return `Jenkins changed this job: +${added} −${removed} parameters.`;
}

export function PresetCardBody({ preset }: { preset: Preset }) {
  const note = driftNote(preset);
  return (
    <>
      {/* The name keeps the line; the mark goes under it when both do not fit. */}
      <div className="flex flex-wrap items-center gap-x-2">
        {/* The column is narrow enough that a long name is cut; hovering gives it back. */}
        <span title={preset.name} className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap font-medium">
          {preset.name}
        </span>
        {preset.destructive && <DestructiveMark className="flex-none" />}
      </div>

      <CardValuesBlock values={presetCardValues(preset)} />

      {note && <DriftLink presetId={preset.id} title={note} />}
    </>
  );
}

export default function PresetCard({ preset }: { preset: Preset }) {
  const drifted = preset.drift !== null;
  const draggable = useDraggable({
    id: `preset:${preset.id}`,
    disabled: drifted,
  });
  // Placed against the window, not the 264px column, which would cut it off.
  const [open, setOpen] = useState<{
    left: number;
    top: number;
    above: boolean;
  } | null>(null);
  // A press on the card is the card's own: its click opens or closes the list.
  const anchor = useRef<HTMLButtonElement>(null);
  const toggle = (card: HTMLElement) => {
    if (open) return setOpen(null);
    const box = card.getBoundingClientRect();
    const above = box.bottom > window.innerHeight * 0.55;
    setOpen({ left: box.left, top: above ? box.top : box.bottom, above });
  };

  // It is placed once, against the window; a scroll would leave it behind.
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(null);
    window.addEventListener("scroll", close, true);
    return () => window.removeEventListener("scroll", close, true);
  }, [open]);
  // A press on the card no longer closes it, so a drag that starts there must.
  const { active } = useDndContext();
  useEffect(() => {
    if (active) setOpen(null);
  }, [active]);
  const sent = Object.entries(preset.params).filter(([, setting]) => setting.mode !== "default");

  return (
    <div
      ref={draggable.setNodeRef}
      style={{ opacity: draggable.isDragging ? 0.4 : 1 }}
      // Only the pointer listeners: the button inside is the one Tab stop, and
      // dnd-kit's own role and "press space" hints describe no key that works here.
      {...(drifted ? {} : draggable.listeners)}
      className="relative"
    >
      <button
        ref={anchor}
        type="button"
        onClick={(event) => toggle(event.currentTarget)}
        className="flex w-full flex-col gap-[5px] rounded-md border border-surface bg-surface px-3 py-[9px] text-left transition-colors duration-150 hover:bg-surface-2"
      >
        <PresetCardBody preset={preset} />
      </button>
      {open && (
        <div className="fixed z-30 h-0 w-0" style={{ left: open.left, top: open.top }}>
          <Menu
            onClose={() => setOpen(null)}
            align="left"
            side={open.above ? "above" : "below"}
            width={420}
            anchor={anchor}
          >
            <div className="flex flex-col gap-2.5 px-3 py-2.5">
              <div className="flex flex-col font-mono text-[13px] leading-[1.7] text-text">
                {sent.map(([name, setting]) => (
                  <div key={name} className="flex gap-2.5">
                    <span className="w-[160px] flex-none text-dim">{name}</span>
                    {setting.mode === "ask" ? (
                      <span className="text-accent">at launch</span>
                    ) : (
                      <span className="min-w-0 whitespace-pre-wrap break-all">
                        {setting.value || <span className="text-dim">empty</span>}
                      </span>
                    )}
                  </div>
                ))}
                {sent.length === 0 && (
                  <span className="text-dim">Every parameter stays on its Jenkins default.</span>
                )}
              </div>
              <div className="flex gap-4 text-[14px]">
                <a
                  href={preset.job_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5"
                >
                  Job in Jenkins <ExternalLink size={13} aria-hidden />
                </a>
                <Link to={`/library/${preset.id}`} role="menuitem">
                  Edit saved job
                </Link>
              </div>
            </div>
          </Menu>
        </div>
      )}
    </div>
  );
}
