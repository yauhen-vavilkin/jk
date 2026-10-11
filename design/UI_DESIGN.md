# JK UI Design

This is the authority for how the JK web panel looks: its colours, its glyphs
and its wording. What each page does is in the README, "The Web Panel".

The machine-readable source of truth is `tokens.json`: colours and glyphs live
there, not in a copy inside a stylesheet. `web/scripts/tokens.mjs` turns it into
the panel's CSS variables and Tailwind colours.

---

## 1. Colour

The palette is the eleven tokens of `palette` plus the six surfaces of
`web_palette`. There are no other colours. Add one only by changing
`tokens.json` and saying why here.

| Token | Hex | Used for |
|---|---|---|
| `bg` | `#111113` | page background |
| `border` | `#3f3f44` | button borders and rules |
| `text` | `#d2d2d6` | primary text, resolved values |
| `key` | `#a8a8ae` | parameter names, job paths, build numbers |
| `dim` | `#85858d` | labels, hints, text-field borders |
| `accent` | `#e0a458` | the current selection, values the user chose |
| `ok` | `#7fa86a` | `SUCCESS`, valid state |
| `info` | `#6f9dbd` | `RUNNING`, links, progress fill |
| `warn` | `#d1705c` | destructive, `FAILURE`, `UNSTABLE`, `ABORTED`, needs attention |
| `link_hover` | `#8fb8d4` | hovered link |
| `track` | `#2e2e33` | hairlines and the unfilled part of a progress bar; the web calls it `hairline` |

| Web token | Hex | Used for |
|---|---|---|
| `surface` | `#17171a` | cards and selected rows |
| `surface_2` | `#1c1c20` | card hover and the parameter-table row divider |
| `well` | `#0e0e10` | inputs and the search field |
| `accent_well` | `#1a1712` | drop indicator and selected candidate background |
| `on_accent` | `#111113` | text on an accent surface |
| `grid` | `#26262b` | the dot grid of the board's flows column |

Rules:

- **Colour carries one meaning.** `warn` means "this can hurt or it went wrong" —
  never decoration. `accent` marks the current selection and what the user typed;
  if everything is accented, nothing is.
  A step card never gets a dashed amber outline: it keeps its usual border, and
  `Fill N values` has a thin solid border and amber text.
- **Never encode state by colour alone.** A failed step says `FAILURE`, a
  destructive job says `destructive`. Colour reinforces the word; it does not
  replace it. Screens get recoloured and people see colour differently.
- `dim` is the darkest grey that still reads as text: at least 4.5:1 on every
  surface it sits on (5.15:1 on `bg`, 4.89:1 on a card, 4.64:1 on a hovered
  one). The panel also draws text-field borders in it, so a field is visible
  against the page; buttons keep `border`.
- The chrome is a cool neutral graphite; only meaning carries colour, and
  saturation is reserved for alarms.

---

## 2. Glyphs

Non-ASCII characters in the panel are a closed set. The panel uses these:

| Glyph | Meaning |
|---|---|
| `…` | a value or label shortened to fit |
| `·` | separates the parts of one line, as in `6 steps · ~42m` |
| `—` | a dash in running text |
| `−` | minus, as in a parameter Jenkins removed |
| `⌘` | the Mac command key in a shortcut hint |

Anything that is pressed, and every status mark, is a Lucide icon, not a glyph:
a font draws its own check mark, and not a good one.

**No emoji. Ever.** Not in a screen, not in a log line, not in a commit that
touches the UI. Emoji look different on every system and read as noise in an
operations tool. `design.test.ts` fails on any non-ASCII character outside the
allowed set.

---

## 3. Writing

The interface is read by a tired engineer at the end of a long pipeline.

- Plain words, short sentences. "The connection dropped while the request was
  being sent" — not "Transport-level failure during submission".
- Say what happened, what it affects, and what the user can do. In that order.
- Jenkins vocabulary stays exact: `SUCCESS`, `FAILURE`, `UNSTABLE`, `ABORTED`,
  `queueId`, and parameter names are never translated or prettified.
- Never apologise and never blame the user.
- No filler rows. If a section is empty, remove the section.
- Nothing offers to send a step again: no Retry, no resend. Where a duplicate
  build is possible, the words stay calm and factual, never urgent — urgency
  makes people click.
