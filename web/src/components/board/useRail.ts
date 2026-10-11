// Below 1280px the saved-jobs column collapses to a rail. Cards never reflow:
// the column goes away, the flow area keeps its width.
import { useEffect, useState } from "react";

const MINIMUM_WIDTH = 1280;
const STORAGE_KEY = "jk.saved-jobs.collapsed";

function stored(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function useRail(): { collapsed: boolean; toggle: () => void } {
  const [collapsed, setCollapsed] = useState(stored);

  useEffect(() => {
    const narrow = window.matchMedia(`(max-width: ${MINIMUM_WIDTH - 1}px)`);
    const apply = () => {
      if (narrow.matches) setCollapsed(true);
    };
    apply();
    narrow.addEventListener("change", apply);
    return () => narrow.removeEventListener("change", apply);
  }, []);

  return {
    collapsed,
    toggle: () =>
      setCollapsed((current) => {
        const next = !current;
        try {
          window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
        } catch {
          // A browser that refuses storage still gets a working toggle.
        }
        return next;
      }),
  };
}
