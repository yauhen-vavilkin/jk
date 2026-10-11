// The editor links the open Jenkins job whatever the tree search shows.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import type { JenkinsJob, Preset } from "@/api/types";
import { SEARCH_PLACEHOLDER } from "./JobsList";
import Library from "./Library";

afterEach(() => vi.restoreAllMocks());

it("keeps the job link while the search hides the job", async () => {
  const url = "https://jenkins.example/job/a/job/createNamespace/";
  const job = { job_path: "a/createNamespace", name: "createNamespace", folder: "a", url } as JenkinsJob;
  const get = vi.spyOn(api, "get").mockImplementation(((path: string) =>
    Promise.resolve(path === "/jenkins/jobs?q=" ? [job] : [])) as typeof api.get);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "/library", element: <Library /> }], {
    initialEntries: ["/library?job=a/createNamespace"],
  });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByRole("link")).toHaveAttribute("href", url));

  fireEvent.change(screen.getByLabelText(SEARCH_PLACEHOLDER), { target: { value: "zzz" } });
  await waitFor(() => expect(get).toHaveBeenCalledWith("/jenkins/jobs?q=zzz"));
  await screen.findByText("No Jenkins job matches that.");

  expect(screen.getByRole("link")).toHaveAttribute("href", url);
});

it("keeps unsaved edits until navigation is explicitly allowed", async () => {
  const saved: Preset = {
    id: "p1",
    name: "Nightly",
    operation: "Rebuild",
    job_path: "a/createNamespace",
    job_url: "",
    destructive: false,
    summary_params: [],
    params: {},
    definitions: [],
    drift: null,
  };
  vi.spyOn(api, "get").mockImplementation(((path: string) =>
    Promise.resolve(path === "/presets" ? [saved] : path.endsWith("/usage") ? { steps: [] } : [])) as typeof api.get);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([
    { path: "/library/:presetId", element: <Library /> },
    { path: "/history", element: <p>History destination</p> },
  ], { initialEntries: ["/library/p1"] });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  const name = await screen.findByRole("textbox", { name: "Saved job name" });
  fireEvent.change(name, { target: { value: "Nightly edited" } });

  await act(() => router.navigate("/history"));
  expect(screen.getByText("Discard changes to Nightly?")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/library/p1");
  fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(name).toHaveValue("Nightly edited");
  expect(screen.queryByText("Discard changes to Nightly?")).toBeNull();

  await act(() => router.navigate("/history"));
  fireEvent.click(screen.getByRole("button", { name: "Discard" }));
  expect(await screen.findByText("History destination")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/history");
});
