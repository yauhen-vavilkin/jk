// Every parameterised job the controller has, as JK last read it, in the
// controller's own folders. Searching narrows the tree and opens what matched;
// the search stays at the top while the tree scrolls under it.
import { Bookmark, ChevronDown, Circle, Plus, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";

import { useRefreshIndex } from "@/api/queries";
import type { JenkinsJob, Preset } from "@/api/types";
import { buildTree, foldersOf, splitTail, type FolderNode } from "./jobTree";

export const SEARCH_PLACEHOLDER = "Search Jenkins jobs…";
const REFRESH_TITLE = "Refresh from Jenkins";

const OPEN_KEY = "jk.library.openFolders";

/** Arrow keys walk the visible rows; right and left open and close a folder. */
function moveInTree(event: React.KeyboardEvent<HTMLDivElement>) {
  const rows = [...event.currentTarget.querySelectorAll<HTMLElement>('[role="treeitem"]')];
  const at = rows.indexOf(document.activeElement as HTMLElement);
  if (at === -1) return;
  const row = rows[at]!;
  const expanded = row.getAttribute("aria-expanded");
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    rows[Math.max(0, Math.min(rows.length - 1, at + (event.key === "ArrowDown" ? 1 : -1)))]?.focus();
  } else if (event.key === "ArrowRight" && expanded === "false") {
    event.preventDefault();
    row.click();
  } else if (event.key === "ArrowLeft" && expanded === "true") {
    event.preventDefault();
    row.click();
  }
}

function remembered(): Set<string> {
  try {
    const raw = window.localStorage.getItem(OPEN_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function remember(open: Set<string>) {
  try {
    window.localStorage.setItem(OPEN_KEY, JSON.stringify([...open]));
  } catch {
    // A browser that keeps nothing still shows the tree; it just starts closed.
  }
}

export default function JobsList({
  jobs,
  error = null,
  query,
  onQuery,
  selected,
  onSelect,
  saved,
}: {
  jobs: JenkinsJob[];
  /** Why the list could not be read; said in place of "no match". */
  error?: string | null;
  query: string;
  onQuery: (next: string) => void;
  selected: string | null;
  onSelect: (job: JenkinsJob) => void;
  saved: SavedUnderJobs;
}) {
  const [open, setOpen] = useState<Set<string>>(remembered);

  // The folder of the job being edited opens by itself. Only a new selection
  // does it, so a folder closed by hand stays closed.
  useEffect(() => {
    const ancestors = foldersOf(selected);
    if (ancestors.every((path) => open.has(path))) return;
    const next = new Set([...open, ...ancestors]);
    setOpen(next);
    remember(next);
  }, [selected]);

  const searching = query.trim() !== "";
  const isOpen = (path: string) => searching || open.has(path);
  const toggle = (path: string) => {
    const next = new Set(open);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setOpen(next);
    remember(next);
  };

  const root = buildTree(jobs);
  const refresh = useRefreshIndex();

  return (
    <div className="flex min-h-0 flex-col border-r border-hairline">
      <div className="m-4 mb-2 flex h-[34px] flex-none items-center gap-2 rounded-md border border-dim bg-well px-2.5 focus-within:border-accent">
        <input
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder={SEARCH_PLACEHOLDER}
          aria-label={SEARCH_PLACEHOLDER}
          className="min-w-0 flex-1 bg-transparent text-[14px] text-text caret-accent outline-hidden placeholder:text-dim"
        />
        <button
          type="button"
          title={REFRESH_TITLE}
          aria-label={REFRESH_TITLE}
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="inline-flex flex-none text-dim transition-colors duration-150 hover:text-text"
        >
          <RotateCw size={14} aria-hidden className={refresh.isPending ? "opacity-45" : ""} />
        </button>
      </div>

      <div
        className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-auto px-4 pb-4 pt-1"
        role="tree"
        aria-label="Jenkins jobs"
        onKeyDown={moveInTree}
      >
        <FolderContents
          node={root}
          depth={0}
          isOpen={isOpen}
          onToggle={toggle}
          selected={selected}
          onSelect={onSelect}
          saved={saved}
        />
        {jobs.length === 0 && (
          <span className="px-2.5 py-2 text-dim">{error ?? "No Jenkins job matches that."}</span>
        )}
      </div>
    </div>
  );
}

const NEW_SAVED_JOB = "New saved job";

/** What is saved for each Jenkins job, and what the tree does with it. */
interface SavedUnderJobs {
  byJob: Map<string, Preset[]>;
  /** The saved job open in the editor, if one is. */
  openId: string | null;
  /** The open saved job, while it has unsaved edits: its row shows a dot. */
  dirtyId?: string | null;
  onOpen: (preset: Preset) => void;
  onNew: (job: JenkinsJob) => void;
}

const INDENT = 16;

function FolderContents({
  node,
  depth,
  isOpen,
  onToggle,
  selected,
  onSelect,
  saved,
}: {
  node: FolderNode;
  depth: number;
  isOpen: (path: string) => boolean;
  onToggle: (path: string) => void;
  selected: string | null;
  onSelect: (job: JenkinsJob) => void;
  saved: SavedUnderJobs;
}) {
  const indent = { paddingLeft: 10 + depth * INDENT };
  return (
    <>
      {node.folders.map((child) => {
        const expanded = isOpen(child.path);
        return (
          <div key={child.path} className="flex flex-col gap-0.5" role="none">
            <button
              type="button"
              role="treeitem"
              aria-expanded={expanded}
              onClick={() => onToggle(child.path)}
              style={indent}
              className="flex items-center gap-2.5 rounded-md py-[7px] pr-2.5 text-left transition-colors duration-150 hover:bg-surface"
            >
              <ChevronDown
                size={14}
                aria-hidden
                className={`flex-none text-dim transition-transform duration-150 ${
                  expanded ? "" : "-rotate-90"
                }`}
              />
              <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-medium">
                {child.name}
              </span>
            </button>
            {expanded && (
              <FolderContents
                node={child}
                depth={depth + 1}
                isOpen={isOpen}
                onToggle={onToggle}
                selected={selected}
                onSelect={onSelect}
                saved={saved}
              />
            )}
          </div>
        );
      })}

      {node.jobs.map((job) => {
        const padding = 10 + depth * INDENT + (depth > 0 ? INDENT : 0);
        // The row of the job is the job as Jenkins has it; what was saved for it is listed under it.
        const current = selected === job.job_path && saved.openId === null;
        const [head, tail] = splitTail(job.name);
        return (
          <div key={job.job_path} className="flex flex-col gap-0.5" role="none">
            <div
              className={`group flex items-center rounded-md transition-colors duration-150 ${
                current ? "bg-surface font-medium" : "hover:bg-surface"
              }`}
            >
              <button
                type="button"
                role="treeitem"
                aria-selected={current}
                onClick={() => onSelect(job)}
                title={job.job_path}
                style={{ paddingLeft: padding }}
                className="flex min-w-0 flex-1 items-center py-2 text-left"
              >
                {/* A long name is cut in the middle: its end tells it from its siblings. */}
                <span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                  {head}
                </span>
                <span className="flex-none whitespace-nowrap">{tail}</span>
              </button>
              <button
                type="button"
                title={NEW_SAVED_JOB}
                aria-label={`${NEW_SAVED_JOB} for ${job.name}`}
                onClick={() => saved.onNew(job)}
                className="inline-flex h-8 w-8 flex-none items-center justify-center text-dim transition-colors duration-150 hover:text-text"
              >
                <Plus size={14} aria-hidden />
              </button>
            </div>
            {(saved.byJob.get(job.job_path) ?? []).map((preset) => (
              <button
                key={preset.id}
                type="button"
                role="treeitem"
                aria-selected={saved.openId === preset.id}
                onClick={() => saved.onOpen(preset)}
                title={preset.name}
                style={{ paddingLeft: padding + INDENT }}
                className={`flex items-center gap-2 rounded-md py-[7px] pr-2.5 text-left transition-colors duration-150 ${
                  saved.openId === preset.id ? "bg-surface font-medium" : "hover:bg-surface"
                }`}
              >
                {preset.drift ? (
                  <span title="Jenkins changed it" className="inline-flex flex-none text-warn">
                    <Bookmark size={14} aria-hidden />
                  </span>
                ) : (
                  <Bookmark size={14} aria-hidden className="flex-none text-dim" />
                )}
                <span className="min-w-0 flex-1 whitespace-normal break-words">
                  {preset.name}
                </span>
                {saved.dirtyId === preset.id && (
                  <Circle size={7} fill="currentColor" aria-hidden className="flex-none" />
                )}
              </button>
            ))}
          </div>
        );
      })}
    </>
  );
}
