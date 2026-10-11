import { describe, expect, it } from "vitest";

import { visibleFlows } from "./visibleFlows";
import type { Flow } from "@/api/types";

function flow(over: Partial<Flow>): Flow {
  return {
    id: "f",
    name: "Flow",
    status: "finished",
    steps: [],
    current_position: null,
    created_at: "",
    started_at: null,
    finished_at: null,
    updated_at: new Date().toISOString(),
    cleared: false,
    failed_at_position: null,
    result: "SUCCESS",
    saved_flow_id: null,
    pinned: false,
    editing: false,
    estimate_ms: null,
    ...over,
  };
}

describe("visibleFlows", () => {
  it("drops a flow the user cleared", () => {
    expect(visibleFlows([flow({ cleared: true })])).toEqual([]);
  });

  it("puts the flow made first at the top, whatever order the list came in", () => {
    const at = (hour: number) => `2026-09-20T0${hour}:00:00Z`;
    const found = visibleFlows([
      flow({ id: "c", status: "draft", created_at: at(3) }),
      flow({ id: "a", status: "running", created_at: at(1) }),
      flow({ id: "b", status: "draft", created_at: at(2) }),
    ]);
    expect(found.map((item) => item.id)).toEqual(["a", "b", "c"]);
  });

  it("orders flows made in the same second by id, so the board never wavers", () => {
    const same = "2026-09-20T01:00:00Z";
    const found = visibleFlows([
      flow({ id: "b", status: "draft", created_at: same }),
      flow({ id: "a", status: "draft", created_at: same }),
    ]);
    expect(found.map((item) => item.id)).toEqual(["a", "b"]);
  });

  it("keeps a pinned flow however long ago it finished, and puts pinned flows first", () => {
    const stale = new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString();
    const found = visibleFlows([
      flow({ id: "a", status: "running" }),
      flow({ id: "b", finished_at: stale, pinned: true }),
      flow({ id: "c", status: "draft" }),
    ]);
    expect(found.map((item) => item.id)).toEqual(["b", "a", "c"]);
  });
});
