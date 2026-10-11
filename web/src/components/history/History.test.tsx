import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import type { Flow } from "@/api/types";
import History from "./History";

afterEach(() => vi.restoreAllMocks());

it("opens recorded step details without an edit action", async () => {
  const flow = { id: "f", name: "Nightly", status: "finished", result: "SUCCESS", steps: [{
    id: "s", position: 0, preset_id: "p", preset_name: "Build", state: "finished", result: "SUCCESS",
    summary: [], run_values: {}, frozen_params: { BRANCH: "main" }, job_url: "https://jenkins.example/job/build/",
  }] } as unknown as Flow;
  vi.spyOn(api, "get").mockResolvedValue([flow]);
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><History /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(await screen.findByRole("button", { name: /Nightly/ }));
  fireEvent.click(screen.getByRole("button", { name: /Step 1, Build/ }));
  expect(screen.getByRole("dialog", { name: "Step 1 details" })).toHaveTextContent("main");
  expect(screen.getByRole("link", { name: "Job in Jenkins" })).toHaveAttribute("href", flow.steps[0]!.job_url);
  expect(screen.queryByRole("link", { name: "Edit saved job" })).not.toBeInTheDocument();
});


it("opens the returned copy for review without waiting for another flow-list request", async () => {
  const flow = { id: "original", name: "Nightly", status: "finished", result: "SUCCESS", steps: [] } as unknown as Flow;
  const copy = { ...flow, id: "copy", name: "Nightly copy", status: "draft" };
  const get = vi.spyOn(api, "get").mockResolvedValueOnce([flow]).mockImplementation(() => new Promise(() => {}));
  const post = vi.spyOn(api, "post").mockResolvedValue(copy);
  function Destination() {
    const state = useLocation().state;
    return <p>{state.review.name} from {state.source}</p>;
  }
  const router = createMemoryRouter([
    { path: "/history", element: <History /> }, { path: "/", element: <Destination /> },
  ], { initialEntries: ["/history"] });
  render(<QueryClientProvider client={new QueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Run again" }));
  expect(await screen.findByText("Nightly copy from original")).toBeInTheDocument();
  expect(post).toHaveBeenCalledWith("/flows/original/rerun", { editing: false, keep_source: true });
  expect(get).toHaveBeenCalledTimes(1);
});
