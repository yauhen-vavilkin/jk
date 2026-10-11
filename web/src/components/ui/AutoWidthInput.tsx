// An input exactly as wide as what it holds, so the row beside it keeps the
// width the design gives it. The sizer is the same text in the same font,
// stacked under the field in one grid cell. It looks like text, so hover
// underlines it and Tab gives it the focus outline every control has.
export default function AutoWidthInput({
  value,
  placeholder,
  label,
  onChange,
  autoFocus = false,
  className = "",
}: {
  value: string;
  placeholder: string;
  label: string;
  onChange: (next: string) => void;
  autoFocus?: boolean;
  className?: string;
}) {
  return (
    <span className="inline-grid max-w-full grid-cols-[minmax(0,max-content)]">
      <span
        aria-hidden
        className={`invisible col-start-1 row-start-1 overflow-hidden whitespace-pre px-px ${className}`}
      >
        {value || placeholder}
      </span>
      <input
        value={value}
        placeholder={placeholder}
        aria-label={label}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
        // size=1 drops the browser's default width of about 20 characters, which
        // would otherwise set the column wider than the text.
        size={1}
        className={`col-start-1 row-start-1 w-full min-w-0 px-px underline-offset-4 placeholder:text-dim hover:underline ${className}`}
      />
    </span>
  );
}
