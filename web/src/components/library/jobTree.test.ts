import { describe, expect, it } from "vitest";

import type { JenkinsJob } from "@/api/types";
import { buildTree, foldersOf, splitTail } from "./jobTree";

function job(job_path: string, run_count = 0): JenkinsJob {
  const segments = job_path.split("/");
  return {
    job_path,
    name: segments[segments.length - 1] ?? "",
    folder: segments.slice(0, -1).join(" / "),
    param_count: 1,
    run_count,
    url: "",
  };
}

describe("the Library tree", () => {
  it("nests jobs in their Jenkins folders and counts every job below a folder", () => {
    const root = buildTree([
      job("folioRancher/manageNamespace/deleteNamespace"),
      job("folioRancher/manageNamespace/createNamespaceFromBranch"),
      job("folioTestingTools/runCypressTests"),
      job("topLevelJob"),
    ]);

    expect(root.total).toBe(4);
    expect(root.jobs.map((item) => item.name)).toEqual(["topLevelJob"]);
    expect(root.folders.map((item) => item.name)).toEqual(["folioRancher", "folioTestingTools"]);
    const rancher = root.folders[0]!;
    expect(rancher.total).toBe(2);
    expect(rancher.jobs).toEqual([]);
    expect(rancher.folders[0]!.path).toBe("folioRancher/manageNamespace");
    expect(rancher.folders[0]!.jobs.map((item) => item.name)).toEqual([
      "createNamespaceFromBranch",
      "deleteNamespace",
    ]);
  });

  it("puts the jobs you run most first inside a folder", () => {
    const root = buildTree([job("tools/alpha"), job("tools/beta", 5)]);

    expect(root.folders[0]!.jobs.map((item) => item.name)).toEqual(["beta", "alpha"]);
  });

  it("names the folders a job sits in, outermost first", () => {
    expect(foldersOf("a/b/job")).toEqual(["a", "a/b"]);
    expect(foldersOf("job")).toEqual([]);
    expect(foldersOf(null)).toEqual([]);
  });
});

describe("a long job name", () => {
  it("keeps its end whole, so siblings with one start stay apart", () => {
    expect(splitTail("createNamespaceFromBranch_PRE_EUREKA")).toEqual([
      "createNamespaceFromBranch",
      "_PRE_EUREKA",
    ]);
    expect(splitTail("createNamespaceFromBranch")).toEqual(["createNamespace", "FromBranch"]);
    expect(splitTail("deleteNamespace")).toEqual(["deleteNamespace", ""]);
    expect(splitTail("runcypresstestsnightly")).toEqual(["runcypresstestsnightly", ""]);
  });
});
