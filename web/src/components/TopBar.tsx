// 56px, one hairline under it: the wordmark and the three pages on the left, the
// host on the right. Every page has the same bar; only the Board has the search.
import { useEffect, useRef } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useJenkinsStatus } from "@/api/queries";
import { clock } from "@/lib/time";
import Search from "./Search";

const NAV = [
  { to: "/", label: "Board" },
  { to: "/library", label: "Library" },
  { to: "/history", label: "History" },
] as const;

type Page = (typeof NAV)[number]["label"];

/** The page a path shows. Any path the panel does not know shows the Board. */
export function pageOf(pathname: string): Page {
  const found = NAV.find((item) => item.to !== "/" && pathname.startsWith(item.to));
  return found?.label ?? "Board";
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** What the Board's search reads from the location: Cmd+K was pressed on another page. */
export interface FocusSearchState {
  focusSearch: true;
}

export default function TopBar({ offlineSince }: { offlineSince: string | null }) {
  const location = useLocation();
  const navigate = useNavigate();
  const status = useJenkinsStatus();
  const page = pageOf(location.pathname);
  const onBoard = location.pathname === "/";
  const host = hostOf(status.data?.url ?? "");
  const searchField = useRef<HTMLInputElement>(null);

  // Cmd+K works on every page: the search lives on the Board, so elsewhere it
  // opens the Board with the cursor already in it.
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k") return;
      event.preventDefault();
      if (onBoard) searchField.current?.focus();
      else navigate("/", { state: { focusSearch: true } satisfies FocusSearchState });
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onBoard, navigate]);

  return (
    <header className="flex min-w-0 flex-col">
      <div className="flex h-14 items-center gap-5 border-b border-hairline px-6">
        <span className="font-mono text-[15px] font-semibold tracking-[.04em] text-accent">JK</span>

        <nav className="flex items-center gap-5">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={`whitespace-nowrap no-underline transition-colors duration-150 ${
                item.label === page ? "border-b-2 border-accent py-4 text-text" : "text-key hover:text-text"
              }`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex-1" />

        {/* While JK itself is gone, what it last said about Jenkins is old news. */}
        {(offlineSince || status.data?.reachable === false) && (
          <span className="min-w-0 truncate text-[14px] text-warn">
            {offlineSince
              ? `JK unreachable since ${clock(offlineSince)} · reconnecting…`
              : `Jenkins unreachable since ${clock(status.data?.since ?? null)} · retrying`}
          </span>
        )}

        {onBoard && <Search field={searchField} />}
        <span className="whitespace-nowrap font-mono text-[13px] text-dim">{host}</span>
      </div>
    </header>
  );
}
