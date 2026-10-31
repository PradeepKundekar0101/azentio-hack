/**
 * The brand block of src/styles/theme.css as constants, for code that cannot read CSS
 * variables: generated share images and icons. Edit theme.css first; brand.test.ts fails
 * until these values match it.
 */
export const brand = {
  ink: "#070b16",
  inkRaised: "#0f1630",
  blue: "#2c41ab",
  blueBright: "#5b6ff0",
  signal: "#f2a33a",
  onInk: "#f4f6fb",
  onInkMuted: "#a3acc2",
} as const;

/**
 * The logo: three ledger lines of a claim, the last one missing a block, and that block
 * fallen below the gap in the signal colour. Money slipping out of the record, caught
 * and made visible. This geometry is the single definition used by the React mark, the
 * favicon (app/icon.svg, checked by brand.test.ts) and the generated share images.
 */
const SIZE = 32;
const BAR = 3; // line thickness; the leaked block is BAR x BAR, so it reads as the missing piece
const LINE_GAP = 2.5;
const LINES: ReadonlyArray<ReadonlyArray<readonly [start: number, end: number]>> = [
  [[8, 24]],
  [[8, 21]],
  [
    [8, 14],
    [18, 24],
  ],
];
const LEAK_X = 14.5; // centred under the gap in the last line (14 to 18)

const contentHeight = LINES.length * (BAR + LINE_GAP) + BAR;
const top = (SIZE - contentHeight) / 2;

const rect = (x: number, y: number, width: number, height: number) => `M${x} ${y}h${width}v${height}h-${width}z`;

export const logoMark = {
  viewBox: `0 0 ${SIZE} ${SIZE}`,
  size: SIZE,
  /** Corner radius of the tile. */
  radius: 8,
  /** The ledger lines, drawn on the tile in brand.onInk. */
  lines: LINES.flatMap((segments, row) =>
    segments.map(([start, end]) => rect(start, top + row * (BAR + LINE_GAP), end - start, BAR)),
  ).join(""),
  /** The leaked block, drawn in brand.signal. */
  leak: rect(LEAK_X, top + LINES.length * (BAR + LINE_GAP), BAR, BAR),
} as const;

const NEAR_RIDGE = "M0 790C300 760 560 690 860 640C1030 612 1190 606 1440 640";

/** The landing backdrop: dune outlines in a 1440 x 1000 scene, anchored to the bottom edge. */
export const scene = {
  width: 1440,
  height: 1000,
  viewBox: "0 0 1440 1000",
  farDune: "M0 640C260 600 520 548 820 552C1040 555 1250 590 1440 612V1000H0Z",
  nearRidge: NEAR_RIDGE,
  nearDune: `${NEAR_RIDGE}V1000H0Z`,
} as const;
