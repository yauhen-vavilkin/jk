// A destructive action asks once, in place, and never in a dialogue of its own.
// It starts on the safe answer, and Escape gives it.
import { useEffect, useRef } from "react";

import { DangerButton } from "./primitives";

export default function InlineConfirm({
  question,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: {
  question: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => cancel.current?.focus(), []);
  return (
    <span
      className="flex items-center gap-2.5 whitespace-nowrap"
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        onCancel();
      }}
    >
      <span className="text-[14px] text-key">{question}</span>
      <DangerButton onClick={onConfirm}>{confirmLabel}</DangerButton>
      <button
        ref={cancel}
        type="button"
        className="text-[14px] text-key hover:text-text"
        onClick={onCancel}
      >
        {cancelLabel}
      </button>
    </span>
  );
}
