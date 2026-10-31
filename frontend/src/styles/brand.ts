/**
 * The brand block of src/styles/theme.css as constants, for code that cannot read CSS
 * variables: generated share images and icons. Edit theme.css first; brand.test.ts fails
 * until these values match it.
 */
export const brand = {
  ink: "#070a12",
  blue: "#2c41ab",
  onInk: "#f3f6fb",
  onInkMuted: "#a9b4c8",
  meshSky: "#0a1b3f",
  meshGlow: "#2f7fe8",
  meshDeep: "#16246b",
  meshLight: "#8ed0ff",
  meshShadow: "#060912",
} as const;

export type BrandColor = keyof typeof brand;

/** `meshSky` -> `var(--brand-mesh-sky)`, for markup that can read CSS variables. */
export const brandVar = (color: BrandColor) => `var(--brand-${color.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)})`;

/**
 * The logo: a drop leaking from a claim form, the product's one-line idea. This geometry
 * is the single definition used by the React mark, the favicon (app/icon.svg, checked by
 * brand.test.ts), the Apple touch icon and the share images.
 */
export const logoMark = {
  viewBox: "0 0 24 24",
  size: 24,
  /** Corner radius of the tile, drawn in brand.blue. */
  radius: 5,
  strokeWidth: 1.6,
  /** The claim form's outline, stroked in brand.onInk. */
  form: "M7.5 5.5h6l3 3v5.25M7.5 5.5v13h4.75",
  /** Two lines of text on the form, stroked in brand.onInk. */
  lines: "M10 9.75h3M10 12.5h2.5",
  /** The drop leaking from the form, filled in brand.onInk. */
  drop: "M16.25 14.25c1.2 1.45 1.95 2.5 1.95 3.4a1.95 1.95 0 0 1-3.9 0c0-.9.75-1.95 1.95-3.4z",
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
    { color: "meshDeep", cx: 760, cy: 760, rx: 700, ry: 200, rotate: -8, opacity: 0.9 },
    { color: "meshGlow", cx: 1220, cy: 520, rx: 600, ry: 270, rotate: -14, opacity: 1 },
    { color: "meshLight", cx: 1310, cy: 470, rx: 250, ry: 105, rotate: -14, opacity: 0.8 },
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
