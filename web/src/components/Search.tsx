// Saved jobs first, then the Jenkins index. Picking a Jenkins job opens Library
// with it selected; picking a saved job opens its editor. The arrow keys walk the
// results and Enter opens the one marked; the cursor stays in the field.
import { useEffect, useId, useState, type RefObject } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useJenkinsJobs, usePresets } from "@/api/queries";
import type { FocusSearchState } from "./TopBar";

const MAX_RESULTS = 8;

export const SEARCH_PLACEHOLDER = "Search saved jobs and Jenkins…";

function shortcutHint(platform: string): string {
  return /mac/i.test(platform) ? "⌘K" : "Ctrl K";
}

/** The result the arrow keys land on: they wrap round at either end. */
export function nextActive(active: number, count: number, key: string): number {
  if (count === 0) return -1;
  if (key === "ArrowDown") return (active + 1) % count;
  if (key === "ArrowUp") return active <= 0 ? count - 1 : active - 1;
  return active;
}

interface Result {
  key: string;
  label: string;
  /** "saved job", or where the Jenkins job lives. */
  note: string;
  saved: boolean;
  to: string;
}

export default function Search({ field }: { field: RefObject<HTMLInputElement> }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  const presets = usePresets();
  const jobs = useJenkinsJobs(query);
  const listId = useId();

  // Cmd+K on another page brings the Board up with the cursor here.
  useEffect(() => {
    if ((location.state as FocusSearchState | null)?.focusSearch) field.current?.focus();
  }, [location.state, field]);

  const needle = query.trim().toLowerCase();
  const savedMatches = (presets.data ?? [])
    .filter((preset) => !needle || preset.name.toLowerCase().includes(needle))
    .slice(0, MAX_RESULTS);
  const results: Result[] = [
    ...savedMatches.map((preset) => ({
      key: preset.id,
      label: preset.name,
      note: "saved job",
      saved: true,
      to: `/library/${preset.id}`,
    })),
    ...(jobs.data ?? []).slice(0, MAX_RESULTS).map((job) => ({
      key: job.job_path,
      label: job.name,
      // Two jobs can share a name; the folder tells them apart.
      note: job.folder || `${job.param_count} parameters`,
      saved: false,
      to: `/library?job=${encodeURIComponent(job.job_path)}`,
    })),
  ];
  const showing = open && needle.length > 0;
  const marked = showing ? Math.min(active, results.length - 1) : -1;
  const optionId = (index: number) => `${listId}-${index}`;

  const pick = (result: Result) => {
    setOpen(false);
    navigate(result.to);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActive(nextActive(marked, results.length, event.key));
    } else if (event.key === "Enter" && marked >= 0) {
      event.preventDefault();
      pick(results[marked]!);
    }
  };

  return (
    <div className="relative">
      <div className="flex h-8 w-[360px] items-center gap-2 overflow-hidden whitespace-nowrap rounded-md border border-dim bg-well px-2.5 text-[14px] transition-colors duration-150 focus-within:border-accent">
        <input
          ref={field}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          placeholder={SEARCH_PLACEHOLDER}
          aria-label={SEARCH_PLACEHOLDER}
          role="combobox"
          aria-expanded={showing}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={marked >= 0 ? optionId(marked) : undefined}
          className="min-w-0 flex-1 caret-accent outline-hidden"
        />
        <span className="ml-auto rounded-sm border border-hairline px-[5px] font-mono text-[12px] text-dim">
          {shortcutHint(navigator.platform)}
        </span>
      </div>

      {showing && (
        <div
          id={listId}
          role="listbox"
          aria-label={SEARCH_PLACEHOLDER}
          className="absolute left-0 top-full z-30 mt-2 flex w-full flex-col rounded-md border border-hairline bg-surface py-1 shadow-[0_8px_24px_rgba(0,0,0,.5)]"
        >
          {results.length === 0 && (
            <div className="px-3 py-2 text-[14px] text-dim">Nothing matches that.</div>
          )}
          {results.map((result, index) => (
            <div
              key={result.key}
              id={optionId(index)}
              role="option"
              aria-selected={index === marked}
              // The cursor stays in the field, so a click does not end the search first.
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActive(index)}
              onClick={() => pick(result)}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-3 py-1.5 text-[14px] ${
                index === marked ? "bg-surface-2" : ""
              }`}
            >
              <span className={result.saved ? "truncate" : "max-w-[65%] flex-none truncate"}>
                {result.label}
              </span>
              <span
                className={`font-mono text-[12px] text-dim ${result.saved ? "shrink-0" : "min-w-0 truncate"}`}
              >
                {result.note}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
