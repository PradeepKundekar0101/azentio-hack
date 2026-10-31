/**
 * The landing page background, drawn rather than photographed: a matte night-blue sky, a
 * horizon glow and two dune lines, with a faint pixel grid and film grain on top. It is
 * resolution independent, costs no image request and takes every colour from the brand
 * tokens in src/styles/theme.css. The dune geometry is shared with the share image.
 */

import { scene } from "@/styles/brand";

// A small SVG noise tile, repeated, gives the matte grain.
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

const stop = (offset: string, color: string, opacity = 1) => (
  <stop offset={offset} style={{ stopColor: color, stopOpacity: opacity }} />
);

export function Backdrop() {
  return (
    <div aria-hidden="true" className="absolute inset-0 -z-10 overflow-hidden bg-brand-ink">
      <svg
        className="absolute inset-0 size-full animate-in duration-[1400ms] ease-out fade-in"
        viewBox={scene.viewBox}
        preserveAspectRatio="xMidYMax slice"
      >
        <defs>
          {/* The sky stays dark on the left, behind the text, and lifts towards the right horizon. */}
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            {stop("0", "var(--brand-ink)")}
            {stop("0.62", "var(--brand-ink-raised)")}
          </linearGradient>
          <radialGradient id="glow" cx="0.74" cy="0.64" r="0.55" gradientTransform="translate(0.74 0.64) scale(1 0.62) translate(-0.74 -0.64)">
            {stop("0", "var(--brand-blue-bright)", 0.9)}
            {stop("0.45", "var(--brand-blue)", 0.55)}
            {stop("1", "var(--brand-blue)", 0)}
          </radialGradient>
          <radialGradient id="sun" cx="0.76" cy="0.63" r="0.16" gradientTransform="translate(0.76 0.63) scale(1 0.5) translate(-0.76 -0.63)">
            {stop("0", "var(--brand-signal)", 0.55)}
            {stop("1", "var(--brand-signal)", 0)}
          </radialGradient>
          <linearGradient id="far" x1="0" y1="0" x2="0" y2="1">
            {stop("0", "var(--brand-ink-raised)")}
            {stop("0.5", "var(--brand-ink)")}
          </linearGradient>
          <linearGradient id="near" x1="0" y1="0.62" x2="0" y2="1">
            {stop("0", "var(--brand-ink-raised)")}
            {stop("0.35", "var(--brand-ink)")}
          </linearGradient>
          <linearGradient id="ridge" x1="0" y1="0" x2="1" y2="0">
            {stop("0.45", "var(--brand-blue-bright)", 0)}
            {stop("0.62", "var(--brand-blue-bright)", 0.5)}
            {stop("0.78", "var(--brand-signal)", 0.9)}
            {stop("1", "var(--brand-signal)", 0.35)}
          </linearGradient>
        </defs>
        <rect width={scene.width} height={scene.height} fill="url(#sky)" />
        <rect width={scene.width} height={scene.height} fill="url(#glow)" />
        <rect width={scene.width} height={scene.height} fill="url(#sun)" />
        <path d={scene.farDune} fill="url(#far)" />
        <path d={scene.nearDune} fill="url(#near)" />
        <path d={scene.nearRidge} fill="none" stroke="url(#ridge)" strokeWidth="1.5" />
      </svg>
      {/* A faint pixel grid in the sky, echoing the pixel type; it fades out before the dunes. */}
      <div className="absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent_60%)] bg-[radial-gradient(circle,rgb(244_246_251/0.09)_1px,transparent_1.5px)] bg-size-[24px_24px]" />
      <div className="absolute inset-0 opacity-[0.2] mix-blend-overlay" style={{ backgroundImage: GRAIN }} />
    </div>
  );
}
