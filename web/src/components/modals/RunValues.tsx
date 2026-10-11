// The values one draft step asks for at launch, typed in a window of their own:
// the card stays one size, and each value is named, described and shown beside
// what Jenkins would use. Nothing is kept until Save, and the window stays open
// until it is: a refusal is read here, with what was typed still in place.
import { useState } from "react";

import type { ParamDefinition, Step } from "@/api/types";
import { needsAValue } from "@/components/library/paramRows";
import SaveButton, { NOTHING_TO_SAVE } from "@/components/ui/SaveButton";
import { QuietButton } from "@/components/ui/primitives";
import Modal from "./Modal";

export const FILL_VALUES = "Fill values";
export const NOT_A_CHOICE = "Not one of the values Jenkins offers";
export const PLACEHOLDER = "Jenkins' placeholder, not a value";
export const FIX_FIRST = "Fix the marked values first";
export const fromStep = (step: number) => `From step ${step}`;

/** A value an earlier step of the flow holds, and that step's number (1-based). */
interface Carried {
  value: string;
  step: number;
}

/**
 * For each parameter, the value the nearest step before `position` holds, so
 * the same value is not typed again in every step. `steps` are in flow order.
 */
export function carriedValues(steps: Step[], position: number): Record<string, Carried> {
  const carried: Record<string, Carried> = {};
  for (const earlier of steps) {
    if (earlier.position >= position) continue;
    for (const [name, value] of Object.entries(earlier.run_values)) {
      if (value.trim()) carried[name] = { value, step: earlier.position + 1 };
    }
  }
  return carried;
}

/**
 * Why Jenkins would refuse this value, or null. An empty value is allowed here:
 * the flow cannot start until it is filled, and it says so itself.
 */
export function wrongValue(value: string, definition: ParamDefinition | undefined): string | null {
  if (!definition || !value.trim()) return null;
  if (definition.type === "CascadeChoiceParameter" && value.trim() === "error") return PLACEHOLDER;
  const choices = definition.choices ?? [];
  if (choices.length > 0 && !choices.includes(value)) return NOT_A_CHOICE;
  return null;
}

export default function RunValues({
  step,
  asked,
  definitions,
  stepCount,
  carried = {},
  onSave,
  onClose,
}: {
  step: Step;
  /** The parameters the step's saved job asks for at launch. */
  asked: string[];
  definitions: ParamDefinition[];
  /** How many steps the flow has, for "step 2 of 6". */
  stepCount?: number;
  /** What earlier steps hold: an empty field starts with it. */
  carried?: Record<string, Carried>;
  /** Settles once the values are kept; the window closes then, not before. */
  onSave: (values: Record<string, string>) => Promise<unknown>;
  onClose: () => void;
}) {
  const own = (name: string) => step.run_values[name] ?? "";
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(asked.map((name) => [name, own(name) || (carried[name]?.value ?? "")])),
  );
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // Nothing to save while every value is the one the step already holds. The
  // window closes once it has saved, so it never needs to read `Saved`.
  const unchanged = asked.every((name) => (values[name] ?? "") === own(name));
  const definitionOf = (name: string) => definitions.find((item) => item.name === name);
  const wrong = asked.some((name) => wrongValue(values[name] ?? "", definitionOf(name)) !== null);
  const save = () => {
    if (saving || unchanged || wrong) return;
    setSaving(true);
    setProblem(null);
    onSave(values).then(
      () => setSaving(false),
      (error: Error) => {
        setSaving(false);
        setProblem(error.message);
      },
    );
  };

  return (
    // While the values are sent the window stays: closed then, a refusal would
    // have nowhere to be read, and Cancel would not have cancelled anything.
    <Modal width={622} top={80} onClose={onClose} locked={saving} label={FILL_VALUES}>
      <form
        className="flex min-h-0 flex-col"
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <div className="flex items-baseline gap-3.5 px-7 pb-4 pt-[22px]">
          <span className="text-[20px] font-semibold">{FILL_VALUES}</span>
          <span className="text-key">
            step {step.position + 1}
            {stepCount ? ` of ${stepCount}` : ""} · {step.preset_name}
          </span>
        </div>

        <div className="flex min-h-0 flex-col gap-4 overflow-auto border-t border-hairline px-7 py-4">
          {asked.map((name, index) => {
            const definition = definitionOf(name);
            const choices = definition?.choices ?? [];
            const value = values[name] ?? "";
            const why = wrongValue(value, definition);
            const from = !own(name) && carried[name]?.value === value ? carried[name] : undefined;
            return (
              <label key={name} className="flex flex-col gap-1.5">
                <span className="font-mono text-[13px] text-text">{name}</span>
                <input
                  value={value}
                  data-autofocus={index === 0 || undefined}
                  list={choices.length > 0 ? `run-value-${name}` : undefined}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [name]: event.target.value }))
                  }
                  aria-invalid={why !== null}
                  className={`h-8 w-full rounded-[5px] border bg-well px-2 font-mono text-[13px] text-text outline-hidden focus:border-accent ${
                    why ? "border-warn" : "border-dim"
                  }`}
                />
                {from && <span className="text-[13px] text-dim">{fromStep(from.step)}</span>}
                {why && <span className="text-[13px] text-warn">{why}</span>}
                {choices.length > 0 && (
                  <datalist id={`run-value-${name}`}>
                    {choices.map((choice) => (
                      <option key={choice} value={choice} />
                    ))}
                  </datalist>
                )}
                {/* Jenkins' `error` placeholder is not a default: it is left unsaid. */}
                {definition?.default && !needsAValue(definition) && (
                  <span className="font-mono text-[12px] text-dim">
                    Jenkins default: {definition.default}
                  </span>
                )}
              </label>
            );
          })}
        </div>

        <div className="flex items-center gap-5 border-t border-hairline px-7 pb-[22px] pt-4">
          {problem && <span className="min-w-0 text-[14px] text-warn">{problem}</span>}
          <div className="flex-1" />
          <QuietButton onClick={onClose} disabled={saving}>
            Cancel
          </QuietButton>
          <SaveButton
            state={saving ? "saving" : "unsaved"}
            disabled={unchanged || wrong}
            title={unchanged ? NOTHING_TO_SAVE : wrong ? FIX_FIRST : undefined}
            submit
          />
        </div>
      </form>
    </Modal>
  );
}
