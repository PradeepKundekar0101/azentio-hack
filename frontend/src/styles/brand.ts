/**
 * The brand block of src/styles/theme.css as constants, for code that cannot read CSS
 * variables: generated share images and icons. Edit theme.css first; brand.test.ts fails
 * until these values match it.
 */
export const brand = {
  ink: "#07090b",
  signal: "#f2a33a",
  onInk: "#f5f1ea",
  onInkMuted: "#b4ada3",
  meshSky: "#0f3236",
  meshEmber: "#c4501a",
  meshWine: "#4a1a10",
  meshShadow: "#120d0c",
} as const;

export type BrandColor = keyof typeof brand;

/** `meshSky` -> `var(--brand-mesh-sky)`, for markup that can read CSS variables. */
export const brandVar = (color: BrandColor) => `var(--brand-${color.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)})`;

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
  /** Corner radius of the tile, drawn in brand.ink. */
  radius: 8,
  /** The ledger lines, drawn on the tile in brand.onInk. */
  lines: LINES.flatMap((segments, row) =>
    segments.map(([start, end]) => rect(start, top + row * (BAR + LINE_GAP), end - start, BAR)),
  ).join(""),
  /** The leaked block, drawn in brand.signal. */
  leak: rect(LEAK_X, top + LINES.length * (BAR + LINE_GAP), BAR, BAR),
} as const;

/**
 * The mesh gradient behind the landing page and the share image, in a 1440 x 1000 scene.
 * Soft colour fields are blurred into each other (the mesh), a dark dune rises on the left
 * where the text sits, and its ridge catches the glow. Film grain is added on top by each
 * renderer. Both renderers read this one definition.
 */
const DUNE_RIDGE = "M-80 540C220 505 520 525 800 600C1060 668 1280 775 1520 900";

export const scene = {
  width: 1440,
  height: 1000,
  viewBox: "0 0 1440 1000",
  /** Blur radius that melts the colour fields into a mesh. */
  meshBlur: 110,
  fields: [
    { color: "meshSky", cx: 260, cy: 180, rx: 950, ry: 560, rotate: 0, opacity: 1 },
    { color: "meshWine", cx: 760, cy: 760, rx: 700, ry: 200, rotate: -8, opacity: 0.9 },
    { color: "meshEmber", cx: 1220, cy: 520, rx: 600, ry: 270, rotate: -14, opacity: 1 },
    { color: "signal", cx: 1310, cy: 470, rx: 250, ry: 105, rotate: -14, opacity: 0.85 },
  ] satisfies ReadonlyArray<{
    color: BrandColor;
    cx: number;
    cy: number;
    rx: number;
    ry: number;
    rotate: number;
    opacity: number;
  }>,
  /** The dune: a lighter blur keeps its edge soft but readable. */
  duneBlur: 14,
  dune: `${DUNE_RIDGE}V1080H-80Z`,
  ridge: DUNE_RIDGE,
} as const;
