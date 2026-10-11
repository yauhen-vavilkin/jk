// The icon button: the fourth shape of the button system. The icon is a Lucide
// component, 16px. With a label it carries the word beside the icon, and that word
// is its name, for a screen reader too, while a title may say more on hover; without
// one the title is all there is to say what it does.
import type { LucideIcon } from "lucide-react";

export default function IconButton({
  icon: Icon,
  title,
  label,
  onClick,
  tone = "normal",
  disabled = false,
  active = false,
  muted = false,
  quiet = false,
  minWidth,
  autoFocus,
}: {
  icon: LucideIcon;
  /** More than the label says, or, without a label, all there is. */
  title?: string;
  /** The word beside the icon. Without it the button stays the 32 by 32 square. */
  label?: string;
  onClick?: () => void;
  tone?: "normal" | "danger";
  disabled?: boolean;
  /** The thing the button turns on is on: it reads in the text colour. */
  active?: boolean;
  /**
   * Off, but still read: it says what just happened, like `Saved`. Off by
   * `aria-disabled`, so a pressed button keeps the focus as it turns into this.
   */
  muted?: boolean;
  /** No frame: a secondary action beside the one framed main button. */
  quiet?: boolean;
  /** A width it keeps whatever its word, so the row beside it does not jump. */
  minWidth?: number;
  /** Takes the focus as it appears: where focus goes back to after an in-place choice. */
  autoFocus?: boolean;
}) {
  // Framed, hover lights the frame; quiet, it lights the word.
  const frame = quiet
    ? ""
    : muted || disabled
      ? "border border-hairline"
      : "border border-border hover:border-dim";
  const colours = muted
    ? "text-dim"
    : disabled
      ? "text-border"
      : tone === "danger"
        ? "text-warn"
        : active
          ? "text-text"
          : `text-key ${quiet ? "hover:text-text" : ""}`;
  return (
    <button
      type="button"
      onClick={muted ? undefined : onClick}
      disabled={disabled}
      aria-disabled={muted || undefined}
      title={title}
      aria-label={label ? undefined : title}
      autoFocus={autoFocus}
      style={minWidth ? { minWidth } : undefined}
      className={`inline-flex h-8 flex-none items-center justify-center gap-1.5 rounded-md transition-colors duration-150 ${
        label ? "px-2.5" : "w-8"
      } ${frame} ${colours}`}
    >
      <Icon size={16} strokeWidth={2} aria-hidden />
      {label && <span className="whitespace-nowrap text-[13px]">{label}</span>}
    </button>
  );
}
