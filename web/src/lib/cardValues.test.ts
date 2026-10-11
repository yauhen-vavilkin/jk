import { describe, expect, it } from "vitest";

import type { ParamSetting, Preset, Step, SummaryValue } from "@/api/types";
import { cardValues, oneLine, presetCardValues, stepValues } from "./cardValues";

const value = (name: string, text: string, per_run = false): SummaryValue => ({
  name,
  value: text,
  per_run,
});

const texts = (summary: SummaryValue[]) =>
  cardValues(summary).lines.map((line) => line.map((item) => item.text));

const fixed = (text: string): ParamSetting => ({ mode: "fixed", value: text, last_value: null });
const ask: ParamSetting = { mode: "ask", value: null, last_value: null };
const left: ParamSetting = { mode: "default", value: "stale", last_value: null };

const preset = (params: Record<string, ParamSetting>, summary_params: string[] = []): Preset =>
  ({ id: "p", params, summary_params, drift: null }) as unknown as Preset;

const step = (patch: Partial<Step>): Step =>
  ({ summary: [], run_values: {}, frozen_params: null, ...patch }) as Step;

describe("cardValues", () => {
  it("collapses CLUSTER and NAMESPACE into one target line", () => {
    const shown = cardValues([value("CLUSTER", "example-cluster"), value("NAMESPACE", "example-ns")]);

    expect(shown.target).toBe("example-cluster / example-ns");
    expect(shown.lines).toEqual([]);
  });

  it("prints the one of the two that is set, alone", () => {
    expect(cardValues([value("NAMESPACE", "example-ns")]).target).toBe("example-ns");
    expect(cardValues([value("TENANT_ID", "diku")]).target).toBeNull();
  });

  it("writes the worker count as words and nothing else by name", () => {
    expect(texts([value("TENANT_ID", "diku"), value("NUMBER_OF_WORKERS", "4")])).toEqual([
      ["diku", "4 workers"],
    ]);
  });

  it("shows four values at most", () => {
    const shown = cardValues(["A", "B", "C", "D", "E"].map((name) => value(name, name.toLowerCase())));

    expect(shown.lines.flat().map((item) => item.name)).toEqual(["A", "B", "C", "D"]);
  });

  it("gives a long value a line of its own", () => {
    expect(texts([value("TENANT_ID", "diku"), value("TAGS", "eureka+smokeECS eureka+critical")])).toEqual(
      [["diku"], ["eureka+smokeECS eureka+critical"]],
    );
  });

  it("leaves every empty value off the value lines", () => {
    expect(cardValues([value("FOLIO_BRANCH", "", true), value("CONFIG_TYPE", "")]).lines).toEqual([]);
  });

  it("names the values still to be typed at launch on a line of their own, target ones included", () => {
    const shown = cardValues(
      [value("CLUSTER", "", true), value("TENANT", "", true)],
      ["CLUSTER", "TENANT"],
    );

    expect(shown.target).toBeNull();
    expect(shown.launch).toBe("CLUSTER · TENANT");
  });

  it("counts them when their names and \"at launch\" do not fit on one line, never cutting one", () => {
    const names = ["PLATFORM", "CLUSTER", "NAMESPACE", "OKAPI_VERSION", "APPLICATIONS"];

    expect(cardValues([], names).launch).toBe("5");
    // 19 characters of names and 10 of " at launch": one more than a line holds.
    expect(cardValues([], ["CLUSTER", "NAMESPACE"]).launch).toBe("2");
    expect(cardValues([], []).launch).toBeNull();
  });

  it("does not let a value asked at launch take one of the four places", () => {
    const shown = cardValues(
      [value("FOLIO_BRANCH", "", true), ...["A", "B", "C", "D"].map((name) => value(name, name))],
      ["FOLIO_BRANCH"],
    );

    expect(shown.lines.flat().map((item) => item.name)).toEqual(["A", "B", "C", "D"]);
  });

  it("carries the whole NAME=value list for the hover title", () => {
    const shown = cardValues([value("CLUSTER", "example-cluster"), value("NUMBER_OF_WORKERS", "4")]);

    expect(shown.title).toBe("CLUSTER=example-cluster\nNUMBER_OF_WORKERS=4");
  });

  it("ends the hover title with every value still to be typed at launch", () => {
    const shown = cardValues(
      [value("CLUSTER", "example-cluster")],
      ["PLATFORM", "APPLICATIONS"],
      [
        { name: "CLUSTER", value: "example-cluster", asked: false },
        { name: "PLATFORM", value: "", asked: true },
        { name: "APPLICATIONS", value: "", asked: true },
      ],
    );

    expect(shown.title).toBe("CLUSTER=example-cluster\nAt launch: PLATFORM, APPLICATIONS");
  });
});

describe("stepValues", () => {
  const job = preset({ CLUSTER: fixed("example-cluster"), BRANCH: ask, APPLICATIONS: ask, LEFT: left });

  it("lists everything a step not sent yet will send, beyond the summary", () => {
    const listed = stepValues(step({ run_values: { BRANCH: "main" } }), job);

    expect(listed).toEqual([
      { name: "CLUSTER", value: "example-cluster", asked: false },
      { name: "BRANCH", value: "main", asked: true },
      { name: "APPLICATIONS", value: "", asked: true },
    ]);
  });

  it("is the body fixed at review once there is one", () => {
    const sent = step({ frozen_params: { CLUSTER: "example-cluster", BRANCH: "main" } });

    expect(stepValues(sent, job, ["BRANCH"])).toEqual([
      { name: "CLUSTER", value: "example-cluster", asked: false },
      { name: "BRANCH", value: "main", asked: true },
    ]);
  });

  it("falls back to the summary and the asked names without the saved job", () => {
    const listed = stepValues(step({ summary: [value("CLUSTER", "example-cluster")] }), undefined, ["BRANCH"]);

    expect(listed).toEqual([
      { name: "CLUSTER", value: "example-cluster", asked: false },
      { name: "BRANCH", value: "", asked: true },
    ]);
  });
});

describe("presetCardValues", () => {
  it("names what a saved job asks at launch and keeps the values it fixes", () => {
    const shown = presetCardValues(
      preset(
        { CLUSTER: ask, NAMESPACE: ask, TENANT_ID: fixed("diku"), LEFT: left },
        ["CLUSTER", "NAMESPACE", "TENANT_ID", "LEFT"],
      ),
    );

    expect(shown.target).toBeNull();
    expect(shown.launch).toBe("2");
    expect(shown.lines.flat().map((item) => item.text)).toEqual(["diku"]);
    expect(shown.title).toBe("TENANT_ID=diku\nAt launch: CLUSTER, NAMESPACE");
  });
});

describe("oneLine", () => {
  it("folds line breaks and runs of spaces into one line", () => {
    expect(oneLine('tags="eureka+smokeECS\neureka+criticalPathECS"\n  env=x')).toBe(
      'tags="eureka+smokeECS eureka+criticalPathECS" env=x',
    );
  });

  it("is empty for a value that is not there", () => {
    expect(oneLine(null)).toBe("");
    expect(oneLine(undefined)).toBe("");
  });
});
