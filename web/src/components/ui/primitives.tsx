// The few shapes every screen is built from: a group label and the four buttons.
import type { ReactNode } from "react";

/** A mono label in the group-heading style: 12px uppercase, wide tracking. */
export function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-1 font-mono text-[12px] uppercase tracking-[.06em] text-dim">{children}</div>
  );
}

/* The whole button system: four shapes, every one 32px high. Size and padding
   belong to the shape, never to a caller's class string: two utilities for the
   same property in one class string are settled by the order Tailwind emits
   them, which is not the order they are written in. */
const BUTTON = "inline-flex h-8 flex-none items-center justify-center whitespace-nowrap rounded-md";

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  /** Why the button is off, for a pointer that rests on it. */
  title?: string;
  /** Takes the focus as it appears: where focus goes back to after an in-place choice. */
  autoFocus?: boolean;
};

export function PrimaryButton({
  children,
  onClick,
  disabled = false,
  title,
  autoFocus,
  focusable = false,
}: ButtonProps & {
  /** Off but still a tab stop, so why it is off (its title) is read on focus too. */
  focusable?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled && !focusable}
      aria-disabled={disabled && focusable ? true : undefined}
      title={title}
      data-why={disabled && focusable ? title : undefined}
      autoFocus={autoFocus}
      className={`${BUTTON} px-4 font-semibold transition-colors duration-150 ${
        disabled ? "bg-border text-dim" : "bg-accent text-on-accent"
      } ${disabled && focusable && title ? "jk-why" : ""}`}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({ children, onClick, disabled = false, title, autoFocus }: ButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      autoFocus={autoFocus}
      className={`${BUTTON} border border-border px-[14px] transition-colors duration-150 ${
        disabled ? "text-dim" : "text-text hover:border-dim"
      }`}
    >
      {children}
    </button>
  );
}

export function DangerButton({ children, onClick, disabled = false, title, autoFocus }: ButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      autoFocus={autoFocus}
      className={`${BUTTON} border px-[14px] transition-colors duration-150 ${
        disabled ? "border-hairline text-dim" : "border-warn text-warn"
      }`}
    >
      {children}
    </button>
  );
}

/** A quiet text link (`Cancel`, `Keep running`): not a button, so no box and no height. */
export function QuietButton({
  children,
  onClick,
  disabled = false,
  autoFocus,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  /** Takes the focus as it appears, as the safe answer of an in-place choice. */
  autoFocus?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      autoFocus={autoFocus}
      className={`whitespace-nowrap transition-colors duration-150 ${
        disabled ? "text-border" : "text-key hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}
