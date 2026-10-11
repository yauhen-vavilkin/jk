// The values block of a card: the target, what is still to be typed at launch,
// then the other values, in mono key. A value asked at launch is accent with a
// dashed underline wherever it appears.
import { SEPARATOR, type CardValues } from "@/lib/cardValues";

const ASKED = "border-b border-dashed border-accent text-accent";

export default function CardValuesBlock({
  values,
  clipped = false,
}: {
  values: CardValues;
  /**
   * Inside a card of a fixed size: a line that does not fit is left out whole,
   * never cut through. The lines wrap into a second column, and that is hidden.
   */
  clipped?: boolean;
}) {
  if (!values.target && !values.launch && values.lines.length === 0) return null;

  return (
    <div
      className={`font-mono text-[13px] leading-normal text-key ${
        clipped ? "flex h-full flex-col flex-wrap content-start overflow-hidden [&>*]:w-full" : ""
      }`}
      title={values.title}
    >
      {values.target && <div className="[overflow-wrap:anywhere]">{values.target}</div>}
      {/* Names are never cut: where the line is short, "at launch" goes under them. */}
      {values.launch && (
        <div>
          <span className={ASKED}>
            {values.launch} <span className="whitespace-nowrap">at launch</span>
          </span>
        </div>
      )}
      {values.lines.map((line) => (
        <div
          key={line.map((item) => item.name).join()}
          className="overflow-hidden text-ellipsis whitespace-nowrap"
        >
          {line.map((item, index) => (
            <span key={item.name}>
              {index > 0 && SEPARATOR}
              {item.perRun ? <span className={ASKED}>{item.text}</span> : item.text}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}
