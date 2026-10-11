// The `sent as` control: three equal segments filling the cell. The chosen
// segment is filled in the colour of what it means; on a row left to Jenkins the whole
// control goes quiet, so what is actually sent reads off the page at a glance.
import type { ParamMode } from "@/api/types";

// The Board's words: a value typed `at launch`, or the Jenkins `default`.
const SEGMENTS: { mode: ParamMode; label: string; chosen: string }[] = [
  { mode: "fixed", label: "fixed", chosen: "bg-text font-medium text-on-accent" },
  { mode: "ask", label: "at launch", chosen: "bg-accent font-medium text-on-accent" },
  { mode: "default", label: "default", chosen: "bg-hairline text-text" },
];

export default function Segmented({
  name,
  value,
  onChange,
}: {
  /** The parameter this belongs to, for a screen reader. */
  name: string;
  value: ParamMode;
  onChange: (mode: ParamMode) => void;
}) {
  return (
    <span
      role="radiogroup"
      aria-label={`${name} is sent as`}
      className={`flex w-full overflow-hidden rounded-[5px] border text-[13px] ${
        value === "default" ? "border-hairline" : "border-border"
      }`}
    >
      {SEGMENTS.map(({ mode, label, chosen }) => (
        <button
          key={mode}
          type="button"
          role="radio"
          aria-checked={value === mode}
          onClick={() => onChange(mode)}
          className={`flex-1 whitespace-nowrap py-[5px] text-center transition-colors duration-150 ${
            value === mode ? chosen : "text-dim hover:text-text"
          }`}
        >
          {label}
        </button>
      ))}
    </span>
  );
}
