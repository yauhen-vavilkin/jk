// Browse every Jenkins job, save your values for one, and repair it when
// Jenkins changes under it.
import { useCallback, useEffect, useRef, useState } from "react";
import { useBlocker, useNavigate, useParams, useSearchParams } from "react-router-dom";

import type { JenkinsJob, ParamDefinition, Preset } from "@/api/types";
import {
  useDefinitions,
  useDeletePreset,
  useDuplicatePreset,
  useJenkinsJobs,
  usePresetUsage,
  usePresets,
  useRepairPreset,
  useSavePreset,
} from "@/api/queries";
import JobsList from "./JobsList";
import PresetEditor, { READING, type EditorValue } from "./PresetEditor";

/** One empty list for a job whose definitions have not come: not a new one per render. */
const NO_DEFINITIONS: ParamDefinition[] = [];

export default function Library() {
  const { presetId } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const presets = usePresets();
  const jobs = useJenkinsJobs(query);
  const index = useJenkinsJobs("");
  const savePreset = useSavePreset();
  const duplicate = useDuplicatePreset();
  const repair = useRepairPreset();
  const deletePreset = useDeletePreset();

  const preset: Preset | null = (presets.data ?? []).find((item) => item.id === presetId) ?? null;
  const usage = usePresetUsage(preset?.id ?? null);

  // The address says what is open, so a move the user is asked about changes
  // nothing until they answer.
  const jobPath = search.get("job");

  // A saved job the user opened is enough on its own; a bare job needs its
  // definitions read from Jenkins before the editor can list anything.
  const definitions = useDefinitions(preset ? null : jobPath);
  const selected = preset?.job_path ?? jobPath;

  // Unsaved edits ask before a move inside the panel (in the editor's header) and
  // before a reload or a closed tab (the browser's own question).
  const unsaved = useRef(false);
  const onDirty = useCallback((next: boolean) => {
    unsaved.current = next;
    setDirty(next);
  }, []);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      unsaved.current &&
      currentLocation.pathname + currentLocation.search !==
        nextLocation.pathname + nextLocation.search,
  );
  useEffect(() => {
    if (!dirty) return;
    const ask = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [dirty]);
  const moveOn = (to: string) => {
    unsaved.current = false;
    navigate(to);
  };

  const onSelect = (job: JenkinsJob) => {
    setProblem(null);
    const existing = (presets.data ?? []).find((item) => item.job_path === job.job_path);
    navigate(existing ? `/library/${existing.id}` : `/library?job=${encodeURIComponent(job.job_path)}`);
  };

  // Every saved job is listed under its Jenkins job, and a job can have another one.
  const savedByJob = new Map<string, Preset[]>();
  for (const item of presets.data ?? []) {
    savedByJob.set(item.job_path, [...(savedByJob.get(item.job_path) ?? []), item]);
  }
  const onNew = (job: JenkinsJob) => {
    setProblem(null);
    navigate(`/library?job=${encodeURIComponent(job.job_path)}`);
  };

  const onSave = (value: EditorValue) => {
    setProblem(null);
    savePreset.mutate(
      {
        id: preset?.id ?? null,
        body: {
          ...(preset ? {} : { job_path: selected }),
          name: value.name,
          operation: value.operation,
          destructive: value.destructive,
          params: value.params,
        },
      },
      {
        // A new saved job moves to its own address; one already there stays put,
        // rather than adding the same page to the history again.
        onSuccess: (saved) => {
          if (!preset) moveOn(`/library/${saved.id}`);
        },
        onError: (error) => setProblem(error instanceof Error ? error.message : String(error)),
      },
    );
  };

  // The original job, for a saved one and for a Jenkins job not saved yet.
  const jobUrl =
    preset?.job_url || (index.data ?? []).find((job) => job.job_path === selected)?.url || "";

  return (
    <main className="grid min-h-0 grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)]">
      <h1 className="sr-only">Library</h1>
      <JobsList
        jobs={jobs.data ?? []}
        error={jobs.error?.message ?? null}
        query={query}
        onQuery={setQuery}
        selected={selected}
        onSelect={onSelect}
        saved={{
          byJob: savedByJob,
          openId: preset?.id ?? null,
          dirtyId: dirty ? (preset?.id ?? null) : null,
          onOpen: (item) => {
            setProblem(null);
            navigate(`/library/${item.id}`);
          },
          onNew,
        }}
      />

      {selected ? (
        <PresetEditor
          key={preset?.id ?? selected}
          preset={preset}
          jobPath={selected}
          jobUrl={jobUrl}
          definitions={preset ? preset.definitions : (definitions.data ?? NO_DEFINITIONS)}
          reading={preset ? null : definitions.isPending ? READING : (definitions.error?.message ?? null)}
          // Only the job the save or repair was sent for says so.
          saving={savePreset.isPending && savePreset.variables?.id === (preset?.id ?? null)}
          repairing={repair.isPending && repair.variables?.id === preset?.id}
          problem={problem}
          usage={usage.data?.steps ?? []}
          onDirty={onDirty}
          leaving={
            blocker.state === "blocked"
              ? { discard: () => blocker.proceed(), keep: () => blocker.reset() }
              : null
          }
          onSave={onSave}
          onDuplicate={() =>
            preset &&
            duplicate.mutate(
              { id: preset.id },
              { onSuccess: (copy) => navigate(`/library/${copy.id}`) },
            )
          }
          onDelete={() =>
            preset &&
            deletePreset.mutate(
              { id: preset.id },
              {
                onSuccess: () => moveOn(`/library?job=${encodeURIComponent(preset.job_path)}`),
                onError: (error) => setProblem(error.message),
              },
            )
          }
          onRepair={(body) =>
            preset &&
            repair.mutate({ id: preset.id, body }, { onError: (error) => setProblem(error.message) })
          }
        />
      ) : (
        <div className="p-7 text-[14px] text-dim">
          Pick a Jenkins job on the left to save your values for it.
        </div>
      )}
    </main>
  );
}
