import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import App from "./App";
import { ApiError } from "./api/client";
import "./index.css";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // Once more, except for a token Jenkins refused: asking again only delays the error.
      retry: (failures, error) => failures < 1 && !(error instanceof ApiError && error.code === "jenkins_auth"),
      staleTime: 5000,
    },
  },
});

// A data router, so a page can hold a navigation back while it has unsaved
// edits (useBlocker). The pages themselves are still routed inside App.
const router = createBrowserRouter([{ path: "*", element: <App /> }]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);
