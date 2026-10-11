import { useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";

import { useEvents } from "./api/events";
import TopBar, { pageOf } from "./components/TopBar";
import Board from "./components/board/Board";
import Library from "./components/library/Library";
import History from "./components/history/History";
import TokenBlock from "./components/TokenBlock";

/** The Board's <main>: the skip link lands there, past the top bar and the saved jobs. */
const FLOWS_ID = "flows";

export default function App() {
  const { offlineSince } = useEvents();
  const page = pageOf(useLocation().pathname);

  useEffect(() => {
    document.title = `${page} · JK`;
  }, [page]);

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)]">
      {page === "Board" && <SkipToFlows />}
      <TopBar offlineSince={offlineSince} />
      <TokenBlock>
        <Routes>
          <Route path="/" element={<Board />} />
          <Route path="/library" element={<Library />} />
          <Route path="/library/:presetId" element={<Library />} />
          <Route path="/history" element={<History />} />
          <Route path="*" element={<Board />} />
        </Routes>
      </TokenBlock>
    </div>
  );
}

/** The first Tab stop on the Board, seen only while it has focus. */
function SkipToFlows() {
  return (
    <a
      href={`#${FLOWS_ID}`}
      onClick={(event) => {
        const flows = document.getElementById(FLOWS_ID);
        if (!flows) return;
        // Focus, not a #hash in the address: the Board reads #flow-<id> as a flow to show.
        event.preventDefault();
        flows.focus();
      }}
      className="sr-only focus:not-sr-only focus:absolute focus:left-6 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-1"
    >
      Skip to flows
    </a>
  );
}
