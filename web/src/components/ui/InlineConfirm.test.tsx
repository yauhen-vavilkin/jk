// An in-place question starts on the safe answer, and Escape gives it.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import InlineConfirm from "./InlineConfirm";

describe("an in-place question", () => {
  it("starts on Keep, and Escape answers Keep", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <InlineConfirm
        question="Delete saved flow?"
        confirmLabel="Delete"
        cancelLabel="Keep"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    const keep = screen.getByRole("button", { name: "Keep" });
    expect(keep).toHaveFocus();

    fireEvent.keyDown(keep, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
