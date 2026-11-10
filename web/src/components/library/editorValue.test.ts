import { describe, expect, it } from "vitest";

import type { Preset } from "@/api/types";
import { rebase, sameEditorValue, seedFrom, signatureOf, summaryToSend, tidy, type EditorValue } from "./editorValue";

const value = (patch: Partial<EditorValue> = {}): EditorValue => ({
  name: "Nightly",
  operation: "Rebuild",
  destructive: false,
  params: {
    CLUSTER: { mode: "fixed", value: "example-cluster", last_value: "example-cluster" },
    NAMESPACE: { mode: "ask", value: null, last_value: "example-ns" },
  },
  summary: null,
  ...patch,
});

describe("nothing to save", () => {
  it("does not see what JK keeps for itself, the order of the parameters, or null against empty", () => {
    const saved = value();
    const shown = value({
      params: {
        NAMESPACE: { mode: "ask", value: "", last_value: "another run" },
        CLUSTER: { mode: "fixed", value: "example-cluster", last_value: null },
      },
    });
    expect(sameEditorValue(shown, saved)).toBe(true);
  });

  it("sees every change the user can make", () => {
    const saved = value();
    const edits: EditorValue[] = [
      value({ name: "Nightly 2" }),
      value({ operation: "Create" }),
      value({ destructive: true }),
      value({ summary: ["NAMESPACE"] }),
      value({ params: { ...saved.params, CLUSTER: { mode: "ask", value: null, last_value: null } } }),
      value({ params: { ...saved.params, CLUSTER: { mode: "fixed", value: "folio-snd", last_value: null } } }),
      value({ params: { ...saved.params, OKAPI: { mode: "fixed", value: "5.0", last_value: null } } }),
      value({ params: { CLUSTER: saved.params.CLUSTER! } }),
    ];
    for (const edit of edits) expect(sameEditorValue(edit, saved)).toBe(false);
  });

  it("gives the same signature to the same saved job, whatever order it arrives in", () => {
    const reordered = value({ params: { NAMESPACE: value().params.NAMESPACE!, CLUSTER: value().params.CLUSTER! } });
    expect(signatureOf(reordered)).toBe(signatureOf(value()));
    expect(signatureOf(value({ name: "Other" }))).not.toBe(signatureOf(value()));
  });
});

describe("a newer copy of the saved job", () => {
  const base = value();
  const theirs = value({
    name: "Renamed elsewhere",
    params: {
      CLUSTER: { mode: "fixed", value: "folio-snd", last_value: "folio-snd" },
      NAMESPACE: { mode: "ask", value: null, last_value: "diku" },
    },
  });

  it("is taken whole when the user changed nothing", () => {
    expect(rebase(base, base, theirs)).toEqual(theirs);
  });

  it("keeps what the user changed and takes the rest, with JK's own last value", () => {
    const mine = value({
      operation: "Mine",
      params: { ...base.params, NAMESPACE: { mode: "fixed", value: "mine", last_value: "example-ns" } },
    });
    const merged = rebase(base, mine, theirs);
    expect(merged.name).toBe("Renamed elsewhere");
    expect(merged.operation).toBe("Mine");
    expect(merged.params.CLUSTER).toEqual(theirs.params.CLUSTER);
    expect(merged.params.NAMESPACE).toEqual({ mode: "fixed", value: "mine", last_value: "diku" });
  });

  it("drops a parameter the newer copy dropped, even one the user changed", () => {
    // A repair takes out what Jenkins no longer defines; the server would refuse it.
    const mine = value({
      params: { ...base.params, NAMESPACE: { mode: "fixed", value: "mine", last_value: "example-ns" } },
    });
    const repaired = value({ params: { CLUSTER: base.params.CLUSTER! } });
    const merged = rebase(base, mine, repaired);
    expect(merged.params).not.toHaveProperty("NAMESPACE");
    expect(sameEditorValue(merged, repaired)).toBe(true);
  });

  it("drops what the newer copy dropped, and keeps what the user removed removed", () => {
    const withoutNamespace = value({ params: { CLUSTER: base.params.CLUSTER! } });
    expect(rebase(base, base, withoutNamespace).params).not.toHaveProperty("NAMESPACE");
    expect(rebase(base, withoutNamespace, theirs).params).not.toHaveProperty("NAMESPACE");
  });
});

describe("a new saved job", () => {
  it("does not take Jenkins' error placeholder as a last value", () => {
    const seeded = seedFrom(null, "folder/job", [
      { name: "CLUSTER", type: "CascadeChoiceParameter", default: "error", choices: null },
      { name: "TENANT", type: "StringParameterDefinition", default: "diku", choices: null },
    ]);
    expect(seeded.params.CLUSTER?.last_value).toBeNull();
    expect(seeded.params.TENANT?.last_value).toBe("diku");
  });
});

describe("the values a card shows", () => {
  const held = { summary_params: ["CLUSTER"], summary_chosen: true } as Preset;

  it("is not sent while nobody chose, or when it is the list the saved job holds", () => {
    expect(summaryToSend(value({ summary: null }), null)).toBeUndefined();
    expect(summaryToSend(value({ summary: ["CLUSTER"] }), held)).toBeUndefined();
  });

  it("is sent once the user chose, even a list of none", () => {
    expect(summaryToSend(value({ summary: ["NAMESPACE"] }), held)).toEqual(["NAMESPACE"]);
    expect(summaryToSend(value({ summary: [] }), held)).toEqual([]);
    expect(summaryToSend(value({ summary: ["CLUSTER"] }), null)).toEqual(["CLUSTER"]);
  });

  it("starts from the saved job's list once it was chosen, and from none chosen otherwise", () => {
    expect(seedFrom(held, "folder/job", []).summary).toEqual(["CLUSTER"]);
    const automatic = { summary_params: ["CLUSTER"], summary_chosen: false } as Preset;
    expect(seedFrom(automatic, "folder/job", []).summary).toBeNull();
    expect(seedFrom(null, "folder/job", []).summary).toBeNull();
  });

  it("keeps the user's choice on a newer copy, and follows the newer copy otherwise", () => {
    const base = value({ summary: ["CLUSTER"] });
    const newer = value({ summary: ["NAMESPACE"] });
    expect(rebase(base, base, newer).summary).toEqual(["NAMESPACE"]);
    expect(rebase(base, value({ summary: [] }), newer).summary).toEqual([]);
  });
});

describe("tidy", () => {
  it("drops the values that are no longer sent from a chosen list, and leaves automatic alone", () => {
    const left = value({
      summary: ["CLUSTER", "NAMESPACE"],
      params: { ...value().params, NAMESPACE: { mode: "default", value: null, last_value: null } },
    });
    expect(tidy(left).summary).toEqual(["CLUSTER"]);
    expect(tidy(value()).summary).toBeNull();
  });
});
