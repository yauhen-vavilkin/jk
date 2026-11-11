import { DndContext } from "@dnd-kit/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Preset, SavedFlow } from "@/api/types";
import SavedJobs from "./SavedJobs";

const job = (name: string, extra: Record<string, unknown> = {}): Preset =>
  ({
    id: name,
    name,
    operation: "",
    job_url: "https://jenkins.example.test/job/example",
    destructive: false,
    summary_params: ["TENANT"],
    params: { TENANT: { mode: "fixed", value: "example-tenant" } },
    drift: null,
    ...extra,
  }) as unknown as Preset;

const flow = (name: string): SavedFlow => ({ id: name, name, steps: [], estimate_ms: null });

const PRESETS = [
  job("create example env sunflower", {
    params: { BRANCH: { mode: "ask", value: "" }, TENANT: { mode: "fixed", value: "example-tenant" } },
  }),
  job("create example env trillium"),
  job("delete example env", { operation: "cleanup", destructive: true }),
];
const FLOWS = [flow("Rebuild and test")];

function wrap(node: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <DndContext>{node}</DndContext>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function column({
  presets = PRESETS,
  savedFlows = FLOWS,
  reveal = null as string | null,
  problem = null as { row: string; text: string } | null,
} = {}) {
  return wrap(
    <SavedJobs
      presets={presets}
      savedFlows={savedFlows}
      onCollapse={() => {}}
      problem={problem}
      onProblem={() => {}}
      reveal={reveal}
    />,
  );
}

const field = () => screen.getByRole("searchbox", { name: "Filter saved jobs" });
const type = (text: string) => fireEvent.change(field(), { target: { value: text } });

describe("the saved jobs column", () => {
  it("shows a job's name and quiet marks, never its values", () => {
    render(column());
    expect(screen.getByText("create example env sunflower")).toBeInTheDocument();
    expect(screen.getByText("1 at launch")).toBeInTheDocument();
    expect(screen.getByText("destructive")).toBeInTheDocument();
    expect(screen.queryByText("example-tenant")).not.toBeInTheDocument();
  });

  it("has no filter while there is nothing to filter", () => {
    render(column({ presets: [], savedFlows: [] }));
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  });

  it("narrows the rows as you type, and drops a group left empty", () => {
    render(column());
    type("trill");
    expect(screen.getByText("create example env trillium")).toBeInTheDocument();
    expect(screen.queryByText("create example env sunflower")).not.toBeInTheDocument();
    expect(screen.queryByText("cleanup")).not.toBeInTheDocument();
    expect(screen.queryByText("Rebuild and test")).not.toBeInTheDocument();
  });

  it("clears on Escape", () => {
    render(column());
    type("trill");
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(field()).toHaveValue("");
    expect(screen.getByText("create example env sunflower")).toBeInTheDocument();
  });

  it("says so when nothing matches, and only then", () => {
    render(column());
    type("nothing like it");
    expect(screen.getByText('Nothing matches "nothing like it".')).toBeInTheDocument();
    type("rebuild");
    expect(screen.getByText("Rebuild and test")).toBeInTheDocument();
    expect(screen.queryByText(/Nothing matches/)).not.toBeInTheDocument();
  });

  it("clears itself when the board is about to show a flow just saved", () => {
    const { rerender } = render(column());
    type("trill");
    rerender(column({ reveal: "Rebuild and test" }));
    expect(field()).toHaveValue("");
    expect(screen.getByText("Rebuild and test")).toBeInTheDocument();
  });

  it("keeps a saved flow with a refusal under it, whatever the filter", () => {
    render(column({ problem: { row: "Rebuild and test", text: "Example refusal." } }));
    type("trill");
    expect(screen.getByText("Rebuild and test")).toBeInTheDocument();
    expect(screen.getByText("Example refusal.")).toBeInTheDocument();
  });
});
