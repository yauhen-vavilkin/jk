// History's times. A run from today reads as a clock time; one from an earlier
// day says which day, because History keeps runs long after the Board has let go.
import type { Flow } from "@/api/types";
import { clock, elapsed } from "@/lib/time";

// Fixed, not from the locale: some write September "Sept", and the rows line up.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "22:31" today, "26 Sep 22:31" on an earlier day, "26 Sep 2025 22:31" in an earlier year. */
export function dayClock(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  if (at.toDateString() === now.toDateString()) return clock(iso);
  const year = at.getFullYear() === now.getFullYear() ? "" : ` ${at.getFullYear()}`;
  return `${at.getDate()} ${MONTHS[at.getMonth()]}${year} ${clock(iso)}`;
}

/** The time on a History row: when the run ended, or when it last changed. */
export function rowTime(flow: Flow, now: Date = new Date()): string {
  return flow.finished_at
    ? `finished ${dayClock(flow.finished_at, now)}`
    : `updated ${dayClock(flow.updated_at, now)}`;
}

/** "started 26 Sep 22:05 · 26m 12s": when an opened run began, and how long it took so far. */
export function startedLine(flow: Flow, now: Date = new Date()): string {
  if (!flow.started_at) return "";
  const end = flow.finished_at ? new Date(flow.finished_at).getTime() : now.getTime();
  const length = elapsed(end - new Date(flow.started_at).getTime());
  return [`started ${dayClock(flow.started_at, now)}`, length].filter(Boolean).join(" · ");
}
