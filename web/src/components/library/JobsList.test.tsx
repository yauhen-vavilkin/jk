// A screen reader names the job tree.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { JenkinsJob, Preset } from "@/api/types";

import JobsList from "./JobsList";

it("names the job tree", () => {
  const saved = { byJob: new Map(), openId: null, onOpen: () => {}, onNew: () => {} };
  render(
    <QueryClientProvider client={new QueryClient()}>
      <JobsList jobs={[]} query="" onQuery={() => {}} selected={null} onSelect={() => {}} saved={saved} />
    </QueryClientProvider>,
  );
  expect(screen.getByRole("tree", { name: "Jenkins jobs" })).toBeInTheDocument();
});


it("shows distinguishing saved-name endings instead of cutting them off", () => {
  const names = ["Daily checks for the example environment alpha", "Daily checks for the example environment beta"];
  const presets = names.map((name, index) => ({ id: `p${index}`, name })) as Preset[];
  const saved = { byJob: new Map([["build", presets]]), openId: null, onOpen: () => {}, onNew: () => {} };
  render(<QueryClientProvider client={new QueryClient()}>
    <JobsList jobs={[{ job_path: "build", name: "build", run_count: 0 } as JenkinsJob]} query="" onQuery={() => {}}
      selected="build" onSelect={() => {}} saved={saved} />
  </QueryClientProvider>);
  for (const name of names) {
    expect(screen.getByRole("treeitem", { name })).toHaveAttribute("title", name);
    expect(screen.getByText(name)).toHaveClass("whitespace-normal", "break-words");
    expect(screen.getByText(name)).not.toHaveClass("overflow-hidden");
  }
});
