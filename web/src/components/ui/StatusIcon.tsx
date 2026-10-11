// The icon beside a status word. Lucide, like everything that is pressed: a font's
// check mark or circle looks different in every typeface, an icon does not.
import { Check, Circle, CircleDashed, Pencil, Square, TriangleAlert } from "lucide-react";

export type StatusIconName = "check" | "running" | "alert" | "stopped" | "editing" | "ready";

export default function StatusIcon({
  name,
  size = 16,
  className = "",
}: {
  name: StatusIconName;
  size?: number;
  /** The role colour, and `jk-pulse` while the thing it marks is going. */
  className?: string;
}) {
  const classes = `inline-block flex-none align-[-0.125em] ${className}`;
  switch (name) {
    case "check":
      return <Check size={size} strokeWidth={2.5} aria-hidden className={classes} />;
    case "running":
      // Filled: a small disc for a running build.
      return <Circle size={size * 0.6} fill="currentColor" aria-hidden className={classes} />;
    case "alert":
      return <TriangleAlert size={size} aria-hidden className={classes} />;
    case "stopped":
      return <Square size={size * 0.7} fill="currentColor" aria-hidden className={classes} />;
    case "editing":
      return <Pencil size={size} aria-hidden className={classes} />;
    // Built, and waiting to be run: an outline of what a running flow fills in.
    case "ready":
      return <CircleDashed size={size} aria-hidden className={classes} />;
  }
}
