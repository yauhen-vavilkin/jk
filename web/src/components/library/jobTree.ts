// The Jenkins index as the controller's own folders. Paths are the job paths JK
// already stores, `folder/sub/job`, so the tree needs nothing new from the API.
import type { JenkinsJob } from "@/api/types";

export interface FolderNode {
  /** The folder's own path, `folioRancher/manageNamespace`; the root's is "". */
  path: string;
  name: string;
  folders: FolderNode[];
  jobs: JenkinsJob[];
  /** Every job under this folder, at any depth. */
  total: number;
}

function folder(path: string, name: string): FolderNode {
  return { path, name, folders: [], jobs: [], total: 0 };
}

/** Folders first by name, then jobs by how often you ran them, then by name. */
export function buildTree(jobs: JenkinsJob[]): FolderNode {
  const root = folder("", "");
  const byPath = new Map<string, FolderNode>([["", root]]);

  for (const job of jobs) {
    const segments = job.job_path.split("/");
    let parent = root;
    parent.total += 1;
    for (let depth = 0; depth < segments.length - 1; depth += 1) {
      const path = segments.slice(0, depth + 1).join("/");
      let child = byPath.get(path);
      if (!child) {
        child = folder(path, segments[depth] ?? "");
        byPath.set(path, child);
        parent.folders.push(child);
      }
      child.total += 1;
      parent = child;
    }
    parent.jobs.push(job);
  }

  for (const node of byPath.values()) {
    node.folders.sort((left, right) =>
      left.name.localeCompare(right.name, undefined, { sensitivity: "base" }),
    );
    node.jobs.sort(
      (left, right) =>
        right.run_count - left.run_count ||
        left.name.localeCompare(right.name, undefined, { sensitivity: "base" }),
    );
  }
  return root;
}

/** The folders a job sits in, outermost first: `a`, `a/b` for `a/b/job`. */
export function foldersOf(jobPath: string | null): string[] {
  if (!jobPath) return [];
  const segments = jobPath.split("/");
  return segments.slice(0, -1).map((_, index) => segments.slice(0, index + 1).join("/"));
}

/** How long the end of a long name that is never cut may be. */
const TAIL = { shortest: 8, longest: 16 };

/**
 * A long name as a head that may be cut and a tail that never is, so a narrow
 * tree reads `createNamespace…_PRE_EUREKA`, not the same start for every
 * sibling. The tail starts where a word does (`_`, `-`, `.`, or a capital after
 * a small letter); a name with no such end is cut at its end as usual.
 */
export function splitTail(name: string): [string, string] {
  const last = Math.max(TAIL.shortest, name.length - TAIL.longest);
  for (let at = name.length - TAIL.shortest; at > last; at -= 1) {
    const here = name[at] ?? "";
    const starts = /[_\-.]/.test(here) || (/[A-Z]/.test(here) && /[a-z]/.test(name[at - 1] ?? ""));
    if (starts) return [name.slice(0, at), name.slice(at)];
  }
  return [name, ""];
}
