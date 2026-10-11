import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import Menu from "./Menu";

function Two({ second, onFirstClose }: { second: boolean; onFirstClose: () => void }) {
  return (
    <>
      <Menu key="first" onClose={onFirstClose}>
        <button type="button" role="menuitem">
          first
        </button>
      </Menu>
      {second && (
        <Menu key="second" onClose={() => {}}>
          <button type="button" role="menuitem">
            second
          </button>
        </Menu>
      )}
    </>
  );
}

function Opened() {
  const opener = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(true);
  return (
    <>
      <button ref={opener} type="button">
        opener
      </button>
      {open && (
        <Menu anchor={opener} onClose={() => setOpen(false)}>
          <button type="button" role="menuitem">
            item
          </button>
        </Menu>
      )}
    </>
  );
}

describe("Menu", () => {
  it("gives focus back to its opener when Escape closes it from inside", () => {
    render(<Opened />);
    screen.getByRole("menuitem").focus();

    fireEvent.keyDown(screen.getByRole("menuitem"), { key: "Escape" });

    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: "opener" })).toHaveFocus();
  });

  it("closes the one that was open when another opens, with no click anywhere", () => {
    const first = vi.fn();
    const { rerender } = render(<Two second={false} onFirstClose={first} />);
    expect(first).not.toHaveBeenCalled();

    rerender(<Two second onFirstClose={first} />);

    expect(first).toHaveBeenCalledTimes(1);
  });
});
