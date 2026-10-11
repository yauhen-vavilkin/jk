// How long something took, and how long it may still take. Jenkins reports only
// an estimate, so everything derived from `estimatedDuration` says "~".

export function elapsed(milliseconds: number | null): string {
  if (milliseconds === null || milliseconds < 0) return "";
  const total = Math.floor(milliseconds / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `${seconds}s`;
}

/** "22m of ~46m": the time so far is real, only the estimate is a guess. */
export function estimateText(elapsedMs: number | null, estimateMs: number | null): string {
  if (elapsedMs === null || estimateMs === null || estimateMs <= 0) return "";
  return `${roundMinutes(elapsedMs)} of ~${roundMinutes(estimateMs)}`;
}

export function roundMinutes(milliseconds: number): string {
  const minutes = Math.floor(milliseconds / 60000);
  if (minutes < 1) return `${Math.max(0, Math.floor(milliseconds / 1000))}s`;
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

/** How full the progress bar is. It never shows more than full. */
export function estimateFraction(elapsedMs: number | null, estimateMs: number | null): number {
  if (elapsedMs === null || estimateMs === null || estimateMs <= 0) return 0;
  return Math.min(1, Math.max(0, elapsedMs / estimateMs));
}

export function clock(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function clockWithSeconds(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
