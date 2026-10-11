import { describe, expect, it } from "vitest";

import {
  DRIFT_BLOCKER,
  PASSWORD_BLOCKER,
  fixedStart,
  placeholderBlocker,
  repairRequest,
  valueNeededBlocker,
  rowsOf,
  saveBlocker,
  suggestsDestructive,
  type ParamRow,
} from "./paramRows";
import type { ParamDefinition, ParamSetting, Preset } from "@/api/types";

function definition(name: string, type = "StringParameterDefinition"): ParamDefinition {
  return { name, type, default: null, choices: null };
}

function setting(mode: ParamSetting["mode"], value: string | null = null): ParamSetting {
  return { mode, value, last_value: null };
}

function preset(over: Partial<Preset> = {}): Preset {
  return {
    id: "p",
    name: "saved job",
    operation: "Create environment",
    job_path: "folder/createNamespace",
    job_url: "",
    destructive: false,
    summary_params: [],
    params: {},
    definitions: [],
    drift: null,
    ...over,
  };
}

describe("rowsOf", () => {
  it("keeps a row in its place whatever is sent for it, and what Jenkins removed last", () => {
    const found = rowsOf(
      preset({
        definitions: [definition("CLUSTER"), definition("PLATFORM"), definition("KONG_VERSION")],
        drift: {
          added: [{ name: "KONG_VERSION", default: "3.9.0", had: null, reason: null }],
          removed: [{ name: "SKIP_REINDEX", default: null, had: "false", reason: null }],
          changed: [],
          seen_at: "",
        },
      }),
      {
        CLUSTER: setting("fixed", "example-cluster"),
        PLATFORM: setting("default"),
        KONG_VERSION: setting("default"),
        SKIP_REINDEX: setting("fixed", "false"),
      },
    );

    expect(found.map((row) => [row.name, row.kind])).toEqual([
      ["CLUSTER", "sent"],
      ["PLATFORM", "default"],
      ["KONG_VERSION", "added"],
      ["SKIP_REINDEX", "removed"],
    ]);
  });

  it("keeps the order Jenkins declares the parameters in", () => {
    const found = rowsOf(
      preset({ definitions: [definition("ZULU"), definition("ALPHA"), definition("MIKE")] }),
      {
        ZULU: setting("fixed", "1"),
        ALPHA: setting("fixed", "2"),
        MIKE: setting("fixed", "3"),
      },
    );

    expect(found.map((row) => row.name)).toEqual(["ZULU", "ALPHA", "MIKE"]);
  });
});

describe("a parameter Jenkins added", () => {
  const drift = {
    added: [{ name: "KONG_VERSION", default: "3.9.0", had: null, reason: null }],
    removed: [{ name: "SKIP_REINDEX", default: null, had: "false", reason: null }],
    changed: [],
    seen_at: "",
  };

  it("has a row, with the Jenkins default, before the change is accepted", () => {
    const [row] = rowsOf(preset({ drift }), {}).filter((item) => item.kind === "added");
    expect(row?.name).toBe("KONG_VERSION");
    expect(row?.mode).toBe("default");
    expect(row?.definition?.default).toBe("3.9.0");
  });

  it("is stored as its row is set when the change is accepted, and a removed one goes", () => {
    const rows = rowsOf(preset({ drift }), {
      KONG_VERSION: setting("fixed", "3.9.1"),
      SKIP_REINDEX: setting("fixed", "false"),
    });
    expect(repairRequest(rows)).toEqual({
      decisions: { KONG_VERSION: "fixed" },
      values: { KONG_VERSION: "3.9.1" },
    });
    expect(repairRequest(rowsOf(preset({ drift }), {}))).toEqual({
      decisions: { KONG_VERSION: "default" },
      values: {},
    });
  });

  it("keeps Save off until the change is accepted, and says where", () => {
    expect(saveBlocker(preset({ drift }), {}, "name")).toBe(DRIFT_BLOCKER);
    expect(DRIFT_BLOCKER).toBe("Accept the Jenkins change above first.");
  });
});

describe("fixedStart", () => {
  const row = (patch: Partial<ParamRow>): ParamRow => ({
    name: "CYPRESS_BRANCH",
    kind: "default",
    mode: "default",
    value: "",
    lastValue: null,
    definition: { ...definition("CYPRESS_BRANCH"), default: "master" },
    isPassword: false,
    ...patch,
  });

  it("starts from the last value, else the Jenkins default", () => {
    expect(fixedStart(row({ lastValue: "develop" }))).toBe("develop");
    expect(fixedStart(row({}))).toBe("master");
    expect(fixedStart(row({ definition: definition("CYPRESS_BRANCH") }))).toBe("");
  });

  it("never starts from Jenkins' error placeholder", () => {
    const cascade = { ...definition("CLUSTER", "CascadeChoiceParameter"), default: "error" };
    expect(fixedStart(row({ definition: cascade, lastValue: "error" }))).toBe("");
  });
});

describe("saveBlocker", () => {
  it("refuses a password parameter with no value", () => {
    const blocked = preset({ definitions: [definition("ADMIN_PASSWORD", "PasswordParameterDefinition")] });
    expect(saveBlocker(blocked, { ADMIN_PASSWORD: setting("fixed", "  ") }, "name")).toBe(
      PASSWORD_BLOCKER,
    );
    expect(saveBlocker(blocked, { ADMIN_PASSWORD: setting("fixed", "swordfish") }, "name")).toBeNull();
  });

  it("refuses a cascade parameter left on Jenkins' error placeholder", () => {
    const blocked = preset({ definitions: [definition("CLUSTER", "CascadeChoiceParameter")] });
    expect(saveBlocker(blocked, { CLUSTER: setting("fixed", " error ") }, "name")).toBe(
      placeholderBlocker("CLUSTER"),
    );
    expect(saveBlocker(blocked, { CLUSTER: setting("fixed", "example-cluster") }, "name")).toBeNull();
  });

  it("keeps error an ordinary value for a parameter that is not cascading", () => {
    const plain = preset({ definitions: [definition("LOG_LEVEL")] });
    expect(saveBlocker(plain, { LOG_LEVEL: setting("fixed", "error") }, "name")).toBeNull();
  });

  it("requires a value for a parameter Jenkins has no default for", () => {
    const job = preset({ definitions: [definition("CLUSTER", "CascadeChoiceParameter")] });
    expect(saveBlocker(job, {}, "name")).toBe(valueNeededBlocker("CLUSTER"));
    expect(saveBlocker(job, { CLUSTER: setting("default") }, "name")).toBe(
      valueNeededBlocker("CLUSTER"),
    );
    expect(saveBlocker(job, { CLUSTER: setting("ask") }, "name")).toBeNull();
    expect(saveBlocker(job, { CLUSTER: setting("fixed", "example-cluster") }, "name")).toBeNull();
  });

  it("leaves a cascade parameter alone once Jenkins declares a default for it", () => {
    const cascade = definition("FOLIO_BRANCH", "CascadeChoiceParameter");
    const declared = { ...cascade, default: "snapshot" };
    expect(saveBlocker(preset({ definitions: [declared] }), {}, "name")).toBeNull();
  });

  it("refuses a saved job with no name", () => {
    expect(saveBlocker(preset(), {}, "  ")).toBe("A saved job needs a name.");
  });
});

describe("suggestsDestructive", () => {
  it("suggests the flag for a job that deletes or recreates a namespace", () => {
    expect(suggestsDestructive("folioRancher/manageNamespace/deleteNamespace")).toBe(true);
    expect(suggestsDestructive("folioRancher/manageNamespace/createNamespaceFromBranch")).toBe(true);
    expect(suggestsDestructive("folioTestingTools/runCypressTests")).toBe(false);
  });
});
