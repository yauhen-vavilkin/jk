// One saved job: its name, whether it is destructive, and what JK sends for
// every parameter Jenkins defines. What it puts on a card is derived by the
// server from what is sent, so nothing here chooses it.
import { Copy, ExternalLink, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { ParamDefinition, ParamSetting, Preset, PresetUse, RepairRequest } from "@/api/types";
import AutoWidthInput from "@/components/ui/AutoWidthInput";
import { DESTRUCTIVE_TITLE } from "@/components/ui/DestructiveMark";
import IconButton from "@/components/ui/IconButton";
import InlineConfirm from "@/components/ui/InlineConfirm";
import SaveButton from "@/components/ui/SaveButton";
import DriftBanner from "./DriftBanner";
import ParamTable from "./ParamTable";
import { rebase, sameEditorValue, seedFrom, signatureOf, type EditorValue } from "./editorValue";
import { repairRequest, rowsOf, saveBlocker } from "./paramRows";

/** Why a new saved job has no parameters yet. */
export const READING = "Reading the job from Jenkins…";

export type { EditorValue } from "./editorValue";

export const DELETE_QUESTION = "Delete saved job?";

/** The flows a Save reaches: `Used by Nightly, step 2 · Rebuild, step 1`. */
export function usedBy(steps: PresetUse[]): string {
  return `Used by ${steps.map((use) => `${use.flow_name}, step ${use.position + 1}`).join(" · ")}`;
}

/** Why the trash is off while a step still uses the saved job. */
export function inUseTitle(steps: PresetUse[]): string {
  return `${usedBy(steps)}. Remove ${steps.length === 1 ? "that step" : "those steps"} first.`;
}

/** Asked before unsaved edits are left behind. */
function discardQuestion(name: string): string {
  return name.trim() ? `Discard changes to ${name}?` : "Discard this new saved job?";
}

export default function PresetEditor({
  preset,
  jobPath,
  jobUrl,
  definitions,
  onSave,
  onDuplicate,
  onDelete,
  onRepair,
  saving,
  repairing,
  problem,
  reading = null,
  usage = [],
  onDirty,
  leaving = null,
}: {
  preset: Preset | null;
  jobPath: string;
  /** The job on the controller, so the original is one click away while filling this in. */
  jobUrl: string;
  definitions: ParamDefinition[];
  onSave: (value: EditorValue) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  /** Accept the Jenkins change, with the new parameters as their rows are set. */
  onRepair: (body: RepairRequest) => void;
  saving: boolean;
  /** A repair is on its way: Save waits for it, and does not claim to be saving. */
  repairing: boolean;
  problem: string | null;
  /** A new saved job's parameters are still being read from Jenkins, or could not be: why the table is empty. */
  reading?: string | null;
  /** The steps that still use this saved job, which a Save reaches. */
  usage?: PresetUse[];
  /** Told whenever the editor starts or stops holding unsaved edits. */
  onDirty?: (dirty: boolean) => void;
  /** Something is about to leave the editor: discard the edits, or stay. */
  leaving?: { discard: () => void; keep: () => void } | null;
}) {
  // The saved job as it is now, and the copy of it the user's edits started from.
  const theirs = seedFrom(preset, jobPath, definitions);
  const signature = signatureOf(theirs);
  const [held, setHeld] = useState(() => ({ signature, base: theirs, value: theirs }));
  // A newer copy -- saved in another tab, repaired, read again -- is taken in as
  // it arrives, during this render: what the user changed stays, the rest follows.
  // Content, not identity, decides, so a list read again with nothing new in it,
  // or a fresh empty array of definitions, changes nothing.
  let current = held;
  if (held.signature !== signature) {
    current = { signature, base: theirs, value: rebase(held.base, held.value, theirs) };
    setHeld(current);
  }
  const value = current.value;
  const setValue = (update: (value: EditorValue) => EditorValue) =>
    setHeld((state) => ({ ...state, value: update(state.value) }));
  const dirty = !sameEditorValue(value, current.base);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    onDirty?.(dirty);
    return () => onDirty?.(false);
  }, [dirty, onDirty]);

  const shown: Preset = preset ?? {
    id: "",
    name: value.name,
    operation: value.operation,
    job_path: jobPath,
    job_url: "",
    destructive: value.destructive,
    summary_params: [],
    params: value.params,
    definitions,
    drift: null,
  };

  const jobName = (preset?.job_path ?? jobPath).split("/").pop() ?? "";
  const blocker = reading ?? saveBlocker(shown, value.params, value.name);
  const rows = rowsOf(shown, value.params);

  const change = (name: string, patch: Partial<ParamSetting>) =>
    setValue((current) => ({
      ...current,
      params: {
        ...current.params,
        [name]: { ...(current.params[name] ?? { mode: "default", value: null, last_value: null }), ...patch },
      },
    }));

  const drop = (name: string) =>
    setValue((current) => {
      const params = { ...current.params };
      delete params[name];
      return { ...current, params };
    });

  return (
    <div className="flex min-w-0 flex-col overflow-auto">
      <div className="flex flex-col gap-4 px-7 pt-5">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3.5">
          <AutoWidthInput
            value={value.name}
            placeholder="Name this saved job"
            label="Saved job name"
            autoFocus={preset === null}
            onChange={(name) => setValue((current) => ({ ...current, name }))}
            className="text-[22px] font-semibold tracking-[-.01em]"
          />
          {/* The name gives up width so the actions stay beside it. */}
          <div className="flex flex-none items-center gap-3.5">
            {/* The discard question is long: it takes the job link's place while it is asked. */}
            {leaving ? null : jobUrl ? (
              <a
                href={jobUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 font-mono text-[13px]"
              >
                {jobName} <ExternalLink size={13} aria-hidden />
              </a>
            ) : (
              <span className="font-mono text-[13px] text-dim">{jobName}</span>
            )}
            {leaving ? (
              <InlineConfirm
                question={discardQuestion(preset?.name ?? value.name)}
                confirmLabel="Discard"
                cancelLabel="Keep editing"
                onConfirm={leaving.discard}
                onCancel={leaving.keep}
              />
            ) : preset && deleting ? (
              <InlineConfirm
                question={DELETE_QUESTION}
                confirmLabel="Delete"
                cancelLabel="Keep"
                onConfirm={() => {
                  setDeleting(false);
                  onDelete();
                }}
                onCancel={() => setDeleting(false)}
              />
            ) : (
              <>
                <SaveButton
                  // Saved only once it exists and holds what is shown; a new job is
                  // always something to save.
                  state={saving ? "saving" : preset && !dirty ? "saved" : "unsaved"}
                  steady
                  disabled={Boolean(blocker) || repairing}
                  title={blocker ?? undefined}
                  onClick={() => onSave(value)}
                />
                {preset && <IconButton icon={Copy} title="Duplicate" onClick={onDuplicate} />}
                {preset && (
                  <IconButton
                    icon={Trash2}
                    // A step that still uses it has to go first; the title names it.
                    title={usage.length > 0 ? inUseTitle(usage) : "Delete saved job"}
                    tone="danger"
                    disabled={usage.length > 0}
                    onClick={() => setDeleting(true)}
                  />
                )}
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-7 whitespace-nowrap text-[14px] text-dim">
          <span className="inline-flex items-center gap-2">
            Operation
            <AutoWidthInput
              value={value.operation}
              placeholder="e.g. Create environment"
              label="Operation"
              onChange={(operation) => setValue((current) => ({ ...current, operation }))}
              className="text-text"
            />
          </span>
          <span className="inline-flex items-center gap-2" title={DESTRUCTIVE_TITLE}>
            Destructive
            <button
              type="button"
              role="switch"
              aria-checked={value.destructive}
              aria-label="Destructive"
              onClick={() =>
                setValue((current) => ({ ...current, destructive: !current.destructive }))
              }
              className={`relative inline-block h-4 w-7 flex-none rounded-full transition-colors duration-150 ${
                value.destructive ? "bg-warn" : "bg-border"
              }`}
            >
              <span
                className={`absolute top-0.5 h-3 w-3 rounded-full bg-bg transition-all duration-150 ${
                  value.destructive ? "right-0.5" : "left-0.5"
                }`}
              />
            </button>
          </span>
        </div>

        {usage.length > 0 && <div className="-mt-2 text-[14px] text-dim">{usedBy(usage)}</div>}

        {preset?.drift && (
          <DriftBanner
            preset={preset}
            onAccept={() => onRepair(repairRequest(rows))}
            busy={saving || repairing}
          />
        )}

        {/* Only what actually went wrong on save. Why Save is off is on the control
            that is off: the name field, or the parameter's own row. */}
        {problem && <div className="text-[14px] text-warn">{problem}</div>}
      </div>

      {reading ? (
        <div className={`px-7 pt-4 text-[14px] ${reading === READING ? "text-dim" : "text-warn"}`}>{reading}</div>
      ) : (
        <ParamTable rows={rows} onChange={change} onDrop={drop} />
      )}
    </div>
  );
}
