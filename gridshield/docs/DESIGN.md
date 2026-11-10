# BlackoutFree Interface Design

## Direction

Keep the existing grid digital twin and its utility-operations identity. The interface uses a quiet, near-black slate canvas, restrained sage-teal accents, and compact instrument-like panels. The city remains the main visual stage; panels provide operational controls and measured simulation output without obscuring what each value represents.

## Tokens

The authoritative tokens live in `frontend/src/index.css`.

| Role | Token | Value |
|---|---|---|
| Canvas | `--night` | `#121a20` |
| City stage | `--scene` | `#18242a` |
| Panel | `--panel` | `#172228` |
| Raised panel | `--panel-strong` | `#1d2a30` |
| Text | `--text` | `#e6eeec` |
| Secondary text | `--muted` | `#b1bfbd` |
| Quiet text | `--quiet` | `#90a09e` |
| Signature accent | `--accent` | `#88b8ab` |
| Normal / protected | `--normal` | `#79b98c` |
| Warning | `--warning` | `#e3b15f` |
| Critical / shed | `--critical` | `#dd8181` |
| Restoring | `--restoring` | `#8db4c7` |

Legacy component aliases (`--green`, `--amber`, `--red`, and `--blue`) resolve to these tokens, so existing status styling stays consistent. The restoring state has its own cool color rather than sharing the accent or warning color.

Contrast ratios against the panel/canvas backgrounds were calculated from these tokens: text 13.74:1 / 14.91:1, muted 8.53:1 / 9.26:1, quiet 5.95:1 / 6.45:1, accent 7.32:1 / 7.95:1, normal 7.05:1 / 7.65:1, warning 8.27:1 / 8.98:1, critical 5.81:1 / 6.31:1, and restoring 7.32:1 / 7.94:1. These exceed WCAG AA for normal text on those surfaces.

## Typography

DM Sans is the UI face and JetBrains Mono is reserved for telemetry, identifiers, and tabular values. Both are self-hosted through the existing `@fontsource` imports.

| Token | Size | Use |
|---|---:|---|
| `--type-xs` | 12 px | Labels, controls, compact panel data |
| `--type-sm` | 13 px | Panel headings and supporting copy |
| `--type-md` | 14 px | Primary interface text |
| `--type-lg` | 16 px | Section-level text |
| `--type-xl` | 20 px | Page-level headings |

Telemetry keeps tabular numerals and a larger frequency readout to make changing measurements easy to scan.

## Layout and interaction

- The top bar keeps product identity, view navigation, API/stream/run state, and data provenance together.
- The frequency readout sits immediately below the top bar, leaving navigation unobstructed. Connection and request alerts stack below it.
- The left rail begins with scenario selection and keeps the primary setup controls and run action together. Detailed disturbance, grid-protection, and restoration tuning is progressively disclosed; hardware integration remains separate and collapsed until needed.
- Stopping an active simulation is visually marked as a destructive action and requires confirmation; the backend retains the run's recorded results.
- The 3D city remains the central visual focus. The right rail summarizes run metrics; the lower edge keeps the frequency response, selected-building inspector, and reasoned event log available.
- At tablet widths the existing panel tabs give each operational surface the full available width. The 3D view, keyboard-selectable buildings, empty states, and reduced-motion preference remain supported.

The layout keeps model output distinct from live measurements: provenance labels, telemetry age, unavailable values, and the explanatory flow-estimate legend remain visible where applicable. Existing loading, empty, offline, and API error feedback is retained.

## Motion and accessibility

Status color is paired with text, focus remains visible on keyboard navigation, and the existing reduced-motion media query suppresses transitions and animation. The advanced tuning panel uses a native disclosure element, preserving keyboard operation and expanded-state semantics.
