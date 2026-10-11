// The values window: a grey Save while nothing changed, Saving… until the values
// are kept, and a refusal read in the window with the typed values in place.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Step } from "@/api/types";
import { NOTHING_TO_SAVE, SAVE, SAVING } from "@/components/ui/SaveButton";
import RunValues, {
  FILL_VALUES,
  FIX_FIRST,
  NOT_A_CHOICE,
  PLACEHOLDER,
  carriedValues,
  fromStep,
  wrongValue,
} from "./RunValues";

const step = { id: "s1", position: 0, preset_name: "Create", run_values: {} } as unknown as Step;
const stepAt = (position: number, run_values: Record<string, string>) =>
  ({ id: `s${position}`, position, preset_name: "Create", run_values }) as unknown as Step;
// Save is off by aria-disabled, never by disabled, so it keeps the focus.
const isOff = (button: HTMLElement) => button.getAttribute("aria-disabled") === "true";

function show(onSave: (values: Record<string, string>) => Promise<unknown>, onClose = () => {}) {
  render(
    <RunValues step={step} asked={["CLUSTER", "NAMESPACE"]} definitions={[]} onSave={onSave} onClose={onClose} />,
  );
}

describe("the values window", () => {
  it("keeps Save grey until a value changes, and grey again once it is changed back", () => {
    show(() => Promise.resolve());
    const save = screen.getByRole("button", { name: SAVE });
    expect(isOff(save)).toBe(true);
    expect(save).toHaveAttribute("title", NOTHING_TO_SAVE);

    fireEvent.change(screen.getByRole("textbox", { name: "CLUSTER" }), { target: { value: "example-cluster" } });
    expect(isOff(screen.getByRole("button", { name: SAVE }))).toBe(false);

    fireEvent.change(screen.getByRole("textbox", { name: "CLUSTER" }), { target: { value: "" } });
    expect(isOff(screen.getByRole("button", { name: SAVE }))).toBe(true);
  });

  it("reads Saving… until the save lands, and shows a refusal with the values kept", async () => {
    let refuse: (error: Error) => void = () => {};
    const onSave = vi.fn(() => new Promise((_, reject) => (refuse = reject)));
    show(onSave);
    fireEvent.change(screen.getByRole("textbox", { name: "CLUSTER" }), { target: { value: "example-cluster" } });

    fireEvent.click(screen.getByRole("button", { name: SAVE }));
    expect(onSave).toHaveBeenCalledWith({ CLUSTER: "example-cluster", NAMESPACE: "" });
    expect(isOff(screen.getByRole("button", { name: SAVING }))).toBe(true);
    // A second press while it saves sends nothing more.
    fireEvent.click(screen.getByRole("button", { name: SAVING }));
    expect(onSave).toHaveBeenCalledTimes(1);

    await act(async () => refuse(new Error("Refused for the test.")));
    expect(screen.getByText("Refused for the test.")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "CLUSTER" })).toHaveValue("example-cluster");
    expect(isOff(screen.getByRole("button", { name: SAVE }))).toBe(false);
  });

  it("cannot be closed while it saves, so a refusal always has somewhere to be read", async () => {
    let refuse: (error: Error) => void = () => {};
    const onClose = vi.fn();
    show(() => new Promise((_, reject) => (refuse = reject)), onClose);
    fireEvent.change(screen.getByRole("textbox", { name: "CLUSTER" }), { target: { value: "example-cluster" } });
    fireEvent.click(screen.getByRole("button", { name: SAVE }));

    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(cancel).toBeDisabled();
    fireEvent.keyDown(document, { key: "Escape" });
    await act(async () => new Promise((resolve) => setTimeout(resolve, 300)));
    expect(onClose).not.toHaveBeenCalled();
    // Nor does it fade out and stay, invisible, over the board.
    expect(screen.getByRole("dialog")).not.toHaveClass("jk-modal-out");

    await act(async () => refuse(new Error("Refused for the test.")));
    expect(screen.getByText("Refused for the test.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
  });
});

describe("what the values window accepts", () => {
  const choice = { name: "PLATFORM", type: "ChoiceParameterDefinition", default: "EUREKA", choices: ["EUREKA", "OKAPI"] };
  const cascade = { name: "NAMESPACE", type: "CascadeChoiceParameter", default: "error", choices: null };

  it("refuses what Jenkins would refuse, and lets an empty value wait", () => {
    expect(wrongValue("EUREKA", choice)).toBeNull();
    expect(wrongValue("eureka", choice)).toBe(NOT_A_CHOICE);
    expect(wrongValue("error", cascade)).toBe(PLACEHOLDER);
    expect(wrongValue("my-namespace", cascade)).toBeNull();
    expect(wrongValue("", choice)).toBeNull();
  });

  it("marks a wrong value and keeps Save off until it is corrected", () => {
    render(
      <RunValues step={step} asked={["PLATFORM"]} definitions={[choice]} onSave={() => Promise.resolve()} onClose={() => {}} />,
    );
    // A field with Jenkins choices is a combobox.
    const field = screen.getByRole("combobox", { name: /PLATFORM/ });

    fireEvent.change(field, { target: { value: "eureka" } });
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(NOT_A_CHOICE)).toBeVisible();
    expect(isOff(screen.getByRole("button", { name: SAVE }))).toBe(true);
    expect(screen.getByRole("button", { name: SAVE })).toHaveAttribute("title", FIX_FIRST);

    fireEvent.change(field, { target: { value: "EUREKA" } });
    expect(screen.queryByText(NOT_A_CHOICE)).toBeNull();
    expect(isOff(screen.getByRole("button", { name: SAVE }))).toBe(false);
  });

  it("says a real Jenkins default, and leaves the error placeholder unsaid", () => {
    const branch = { name: "BRANCH", type: "StringParameterDefinition", default: "folio-etesting", choices: null };
    render(
      <RunValues step={step} asked={["NAMESPACE", "BRANCH"]} definitions={[cascade, branch]} onSave={() => Promise.resolve()} onClose={() => {}} />,
    );
    expect(screen.getByText("Jenkins default: folio-etesting")).toBeVisible();
    expect(screen.queryByText("Jenkins default: error")).toBeNull();
  });
});

describe("typing in the values window", () => {
  it("opens with the cursor in the first field, and gives it back to what opened it", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();

    const { unmount } = render(
      <RunValues step={step} asked={["CLUSTER", "NAMESPACE"]} definitions={[]} onSave={() => Promise.resolve()} onClose={() => {}} />,
    );
    expect(screen.getByRole("textbox", { name: "CLUSTER" })).toHaveFocus();
    expect(screen.getByRole("dialog", { name: FILL_VALUES })).toBeVisible();

    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });

  it("saves on Enter, and only when Save is on", async () => {
    const onSave = vi.fn(() => Promise.resolve());
    show(onSave);
    const form = screen.getByRole("textbox", { name: "CLUSTER" }).closest("form")!;

    fireEvent.submit(form);
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole("textbox", { name: "CLUSTER" }), { target: { value: "example-cluster" } });
    await act(async () => fireEvent.submit(form));
    expect(onSave).toHaveBeenCalledWith({ CLUSTER: "example-cluster", NAMESPACE: "" });
  });
});

describe("a flow of several steps", () => {
  it("names the step with the flow's length", () => {
    render(
      <RunValues step={stepAt(1, {})} stepCount={6} asked={["CLUSTER"]} definitions={[]} onSave={() => Promise.resolve()} onClose={() => {}} />,
    );
    expect(screen.getByText("step 2 of 6 · Create")).toBeVisible();
  });

  it("carries the nearest earlier step's value, never a later one or an empty one", () => {
    const steps = [
      stepAt(0, { CLUSTER: "example-cluster", NAMESPACE: "example-ns" }),
      stepAt(1, { CLUSTER: "folio-etesting", NAMESPACE: " " }),
      stepAt(2, {}),
      stepAt(3, { CLUSTER: "later" }),
    ];
    expect(carriedValues(steps, 2)).toEqual({
      CLUSTER: { value: "folio-etesting", step: 2 },
      NAMESPACE: { value: "example-ns", step: 1 },
    });
    expect(carriedValues(steps, 0)).toEqual({});
  });

  it("starts an empty field with a carried value, says where it came from, and saves it", async () => {
    const onSave = vi.fn(() => Promise.resolve());
    render(
      <RunValues
        step={stepAt(1, { NAMESPACE: "mine" })}
        asked={["CLUSTER", "NAMESPACE"]}
        definitions={[]}
        carried={{ CLUSTER: { value: "example-cluster", step: 1 }, NAMESPACE: { value: "example-ns", step: 1 } }}
        onSave={onSave}
        onClose={() => {}}
      />,
    );
    const cluster = screen.getByRole("textbox", { name: /CLUSTER/ });
    expect(cluster).toHaveValue("example-cluster");
    // The step's own value wins, and is not said to come from anywhere.
    expect(screen.getByRole("textbox", { name: /NAMESPACE/ })).toHaveValue("mine");
    expect(screen.getAllByText(fromStep(1))).toHaveLength(1);

    await act(async () => fireEvent.click(screen.getByRole("button", { name: SAVE })));
    expect(onSave).toHaveBeenCalledWith({ CLUSTER: "example-cluster", NAMESPACE: "mine" });

    fireEvent.change(cluster, { target: { value: "folio-perf" } });
    expect(screen.queryByText(fromStep(1))).toBeNull();
  });
});
