/**
 * The landing page background: a mesh gradient (colour fields blurred into each other), a
 * dark dune on the left behind the text with a glowing ridge, and film grain on top.
 * Shapes come from `scene` in src/styles/brand.ts (shared with the share image) and every
 * colour from the brand tokens in src/styles/theme.css. No image request.
 */

import { cn } from "@/lib/utils";
import { brandVar, scene } from "@/styles/brand";

// Film grain: an SVG noise tile, repeated. Two blend layers give the matte, printed look.
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

export function Backdrop({
  className,
  tinted = true,
}: {
  className?: string;
  /** Paint the ink canvas under the mesh (off when the mesh sits over the app canvas). */
  tinted?: boolean;
}) {
  return (
    <div aria-hidden="true" className={cn("absolute inset-0 -z-10 overflow-hidden", tinted && "bg-brand-ink", className)}>
      <svg
        className="absolute inset-0 size-full animate-in duration-[1600ms] ease-out fade-in"
        viewBox={scene.viewBox}
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <filter id="mesh" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation={scene.meshBlur} />
          </filter>
          <filter id="dune" x="-10%" y="-10%" width="120%" height="120%">
            <feGaussianBlur stdDeviation={scene.duneBlur} />
          </filter>
          <linearGradient id="ridge" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0.3" style={{ stopColor: brandVar("meshGlow"), stopOpacity: 0 }} />
            <stop offset="0.7" style={{ stopColor: brandVar("meshGlow"), stopOpacity: 0.9 }} />
            <stop offset="0.9" style={{ stopColor: brandVar("meshLight"), stopOpacity: 0.9 }} />
          </linearGradient>
        </defs>
        <g filter="url(#mesh)">
          {scene.fields.map((field, i) => (
            <ellipse
              key={field.color}
              className={`mesh-drift mesh-drift-${i}`}
              cx={field.cx}
              cy={field.cy}
              rx={field.rx}
              ry={field.ry}
              transform={`rotate(${field.rotate} ${field.cx} ${field.cy})`}
              style={{ fill: brandVar(field.color), opacity: field.opacity }}
            />
          ))}
        </g>
        <g filter="url(#dune)">
          <path d={scene.ridge} fill="none" stroke="url(#ridge)" strokeWidth="10" />
          <path d={scene.dune} style={{ fill: brandVar("meshShadow") }} />
        </g>
      </svg>
      <div className="absolute inset-0 opacity-[0.35] mix-blend-overlay" style={{ backgroundImage: GRAIN }} />
      <div className="absolute inset-0 opacity-[0.12] mix-blend-soft-light" style={{ backgroundImage: GRAIN }} />
    </div>
  );
}
