// The saved job's Save says whether there is anything to save, and an edit
// survives the saved job changing elsewhere while it is open.
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ParamDefinition, Preset } from "@/api/types";
import { SAVE, SAVED, SAVING } from "@/components/ui/SaveButton";
import { ACCEPT_LABEL } from "./DriftBanner";
import PresetEditor, { DELETE_QUESTION, inUseTitle, usedBy } from "./PresetEditor";

const preset = (patch: Partial<Preset> = {}): Preset => ({
  id: "p1",
  name: "Nightly",
  operation: "Rebuild",
  job_path: "folioRancher/manageNamespace/createNamespaceFromBranch",
  job_url: "",
  destructive: false,
  summary_params: [],
  params: { CLUSTER: { mode: "ask", value: null, last_value: "old" } },
  definitions: [],
  drift: null,
  ...patch,
});

const nothing = () => {};
type Props = ComponentProps<typeof PresetEditor>;

function editor(props: Partial<Props>) {
  const all: Props = {
    preset: preset(),
    jobPath: "folioRancher/manageNamespace/createNamespaceFromBranch",
    jobUrl: "",
    definitions: [],
    onSave: nothing,
    onDuplicate: nothing,
    onDelete: nothing,
    onRepair: nothing,
    saving: false,
    repairing: false,
    problem: null,
    ...props,
  };
  return <MemoryRouter><PresetEditor {...all} /></MemoryRouter>;
}

const name = () => screen.getByRole("textbox", { name: "Saved job name" });
/** Off either way a button can be: Save stays focusable with aria-disabled. */
const off = (label: string) => {
  const button = screen.getByRole("button", { name: label }) as HTMLButtonElement;
  return button.disabled || button.getAttribute("aria-disabled") === "true";
};
const operation = () => screen.getByRole("textbox", { name: "Operation" });

describe("the saved job's Save", () => {
  it("reads Saved until something changes, and Saved again once it is changed back", () => {
    render(editor({}));
    expect(off(SAVED)).toBe(true);

    fireEvent.change(name(), { target: { value: "Nightly 2" } });
    expect(off(SAVE)).toBe(false);

    fireEvent.change(name(), { target: { value: "Nightly" } });
    expect(off(SAVED)).toBe(true);
  });

  it("reads Saving… while the save is on its way, and Saved once it comes back", () => {
    const { rerender } = render(editor({}));
    fireEvent.change(name(), { target: { value: "Nightly 2" } });
    rerender(editor({ saving: true }));
    expect(off(SAVING)).toBe(true);

    rerender(editor({ saving: false, preset: preset({ name: "Nightly 2" }) }));
    expect(off(SAVED)).toBe(true);
  });

  it("keeps an edit when the saved job changes elsewhere, and takes the rest of the change", () => {
    const { rerender } = render(editor({}));
    fireEvent.change(operation(), { target: { value: "Mine" } });

    rerender(editor({ preset: preset({ name: "Renamed elsewhere", job_url: "https://jenkins.invalid/x" }) }));

    expect(operation()).toHaveValue("Mine");
    expect(name()).toHaveValue("Renamed elsewhere");
    expect(off(SAVE)).toBe(false);
  });

  it("sends JK's newest last value along with the edit", () => {
    const onSave = vi.fn();
    const { rerender } = render(editor({ onSave }));
    fireEvent.change(operation(), { target: { value: "Mine" } });
    const newer = preset({ params: { CLUSTER: { mode: "ask", value: null, last_value: "new" } } });
    rerender(editor({ onSave, preset: newer }));

    fireEvent.click(screen.getByRole("button", { name: SAVE }));

    expect(onSave.mock.calls[0]?.[0].params.CLUSTER.last_value).toBe("new");
    expect(onSave.mock.calls[0]?.[0].operation).toBe("Mine");
  });

  it("keeps a new job's name while its definitions are on their way, and when they come", () => {
    const fresh = { preset: null, definitions: [] as ParamDefinition[] };
    const { rerender } = render(editor(fresh));
    fireEvent.change(name(), { target: { value: "Fresh" } });

    rerender(editor({ ...fresh, definitions: [] }));
    expect(name()).toHaveValue("Fresh");

    const came = [{ name: "CLUSTER", type: "StringParameterDefinition", default: "example-cluster", choices: null }];
    rerender(editor({ ...fresh, definitions: came }));
    expect(name()).toHaveValue("Fresh");
  });
});

describe("a new saved job", () => {
  it("starts in its name field, and Save says why it is off from the start", () => {
    render(editor({ preset: null }));
    expect(name()).toHaveFocus();
    expect(screen.getByRole("button", { name: SAVE })).toHaveAttribute(
      "title",
      "A saved job needs a name.",
    );
  });
});

describe("where the saved job is used", () => {
  const usage = [
    { flow_id: "f1", flow_name: "Nightly Cypress on trillium", position: 1 },
    { flow_id: "f2", flow_name: "Rebuild from my branch and test", position: 1 },
  ];

  it("names each flow and step under the Operation line", () => {
    render(editor({ usage }));
    expect(
      screen.getByText(
        "Used by Nightly Cypress on trillium, step 2 · Rebuild from my branch and test, step 2",
      ),
    ).toBeInTheDocument();
  });

  it("keeps the trash off while a step uses it, and says which step to remove", () => {
    render(editor({ usage: usage.slice(0, 1) }));
    const trash = screen.getByRole("button", { name: inUseTitle(usage.slice(0, 1)) });
    expect(trash).toBeDisabled();
    expect(inUseTitle(usage.slice(0, 1))).toBe(
      "Used by Nightly Cypress on trillium, step 2. Remove that step first.",
    );
  });

  it("says nothing, and lets the trash ask, when no step uses it", () => {
    render(editor({ usage: [] }));
    expect(screen.queryByText(/^Used by/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Delete saved job" }));
    expect(screen.getByText(DELETE_QUESTION)).toBeInTheDocument();
  });

  it("joins several uses with a middle dot", () => {
    expect(usedBy(usage)).toContain(" · ");
  });
});

describe("leaving with unsaved edits", () => {
  it("reports the edits, and asks in the header before they are discarded", () => {
    const onDirty = vi.fn();
    const discard = vi.fn();
    const { rerender } = render(editor({ onDirty }));
    fireEvent.change(name(), { target: { value: "Nightly 2" } });
    expect(onDirty).toHaveBeenLastCalledWith(true);

    rerender(editor({ onDirty, leaving: { discard, keep: nothing } }));
    expect(screen.getByText("Discard changes to Nightly?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(discard).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Keep editing" })).toBeInTheDocument();
  });

  it("asks about a new saved job with no name as a new saved job", () => {
    render(editor({ preset: null, leaving: { discard: nothing, keep: nothing } }));
    expect(screen.getByText("Discard this new saved job?")).toBeInTheDocument();
  });
});

describe("a Jenkins change", () => {
  it("stores the new parameters as their rows are set with one Accept", () => {
    const onRepair = vi.fn();
    const drifted = preset({
      params: {},
      definitions: [
        { name: "KONG_VERSION", type: "StringParameterDefinition", default: "3.9.0", choices: null },
      ],
      drift: {
        added: [
          { name: "KONG_VERSION", default: "3.9.0", had: null, reason: null },
          { name: "ENTITLEMENT_MODE", default: "STATE", had: null, reason: null },
        ],
        removed: [],
        changed: [],
        seen_at: "2026-09-30T10:00:00Z",
      },
    });
    render(editor({ preset: drifted, onRepair }));

    // "set value" starts from the Jenkins default, even for a parameter the saved
    // definitions do not hold yet.
    fireEvent.click(screen.getAllByRole("button", { name: "set value" })[1]!);
    expect(screen.getByRole("textbox", { name: "Value for ENTITLEMENT_MODE" })).toHaveValue("STATE");
    fireEvent.click(screen.getByRole("button", { name: ACCEPT_LABEL }));

    expect(onRepair).toHaveBeenCalledWith({
      decisions: { KONG_VERSION: "default", ENTITLEMENT_MODE: "fixed" },
      values: { ENTITLEMENT_MODE: "STATE" },
    });
  });
});

describe("a choice parameter's value list", () => {
  it("closes with a second press on its own button", () => {
    const listed = preset({
      params: { ENV: { mode: "fixed", value: "a", last_value: null } },
      definitions: [{ name: "ENV", type: "ChoiceParameterDefinition", default: "a", choices: ["a", "b"] }],
    });
    render(editor({ preset: listed, definitions: listed.definitions }));
    const button = screen.getByRole("button", { name: /^Value for ENV/ });
    fireEvent.click(button);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    fireEvent.mouseDown(button);
    fireEvent.click(button);

    expect(screen.queryByRole("menu")).toBeNull();
  });
});
