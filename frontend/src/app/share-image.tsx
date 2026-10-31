import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { ImageResponse } from "next/og";

import { PRODUCT_NAME } from "@/components/brand";
import { brand, logoMark, scene } from "@/styles/brand";

/**
 * The link-preview card for every page (Open Graph and X/Twitter): the landing page's
 * backdrop, logo and headline at 1200 x 630. Colours and geometry come from
 * src/styles/brand.ts, so the card always matches the site.
 */
export const shareImage = {
  alt: `${PRODUCT_NAME}: find the leakage in every claim`,
  size: { width: 1200, height: 630 },
  contentType: "image/png",
} as const;

// ImageResponse reads ttf, not woff2; the .ttf is the same vendored Geist Pixel face.
const geistPixel = readFile(join(process.cwd(), "src/styles/fonts/GeistPixel-Square.ttf"));

// The landing backdrop as a standalone SVG: same mesh fields, dune and ridge, with grain.
const fields = scene.fields
  .map(
    (f) =>
      `<ellipse cx="${f.cx}" cy="${f.cy}" rx="${f.rx}" ry="${f.ry}" transform="rotate(${f.rotate} ${f.cx} ${f.cy})" fill="${brand[f.color]}" opacity="${f.opacity}"/>`,
  )
  .join("");

const backdrop = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${scene.viewBox}" width="${shareImage.size.width}" height="${shareImage.size.height}" preserveAspectRatio="xMidYMid slice">
  <defs>
    <filter id="mesh" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${scene.meshBlur}"/></filter>
    <filter id="dune" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="${scene.duneBlur}"/></filter>
    <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>
    <linearGradient id="ridge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0.3" stop-color="${brand.meshEmber}" stop-opacity="0"/>
      <stop offset="0.7" stop-color="${brand.meshEmber}" stop-opacity="0.9"/>
      <stop offset="0.9" stop-color="${brand.signal}" stop-opacity="0.8"/>
    </linearGradient>
  </defs>
  <rect x="-200" y="-200" width="${scene.width + 400}" height="${scene.height + 400}" fill="${brand.ink}"/>
  <g filter="url(#mesh)">${fields}</g>
  <g filter="url(#dune)">
    <path d="${scene.ridge}" fill="none" stroke="url(#ridge)" stroke-width="10"/>
    <path d="${scene.dune}" fill="${brand.meshShadow}"/>
  </g>
  <rect width="${scene.width}" height="${scene.height}" filter="url(#grain)" opacity="0.07"/>
</svg>`;

const backdropSrc = `data:image/svg+xml;base64,${Buffer.from(backdrop).toString("base64")}`;

export async function renderShareImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "64px 72px",
        backgroundColor: brand.ink,
        color: brand.onInk,
        fontFamily: "Geist Pixel",
        position: "relative",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- ImageResponse renders plain img only */}
      <img
        src={backdropSrc}
        alt=""
        width={shareImage.size.width}
        height={shareImage.size.height}
        style={{ position: "absolute", top: 0, left: 0 }}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        <svg width="56" height="56" viewBox={logoMark.viewBox}>
          <rect width={logoMark.size} height={logoMark.size} rx={logoMark.radius} fill={brand.ink} />
          <path d={logoMark.lines} fill={brand.onInk} />
          <path d={logoMark.leak} fill={brand.signal} />
        </svg>
        <div style={{ fontSize: 30, letterSpacing: 1 }}>{PRODUCT_NAME.toUpperCase()}</div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        <div style={{ fontSize: 84, lineHeight: 1.02, maxWidth: 820 }}>FIND THE LEAKAGE IN EVERY CLAIM</div>
        <div style={{ fontSize: 28, lineHeight: 1.35, maxWidth: 820, color: brand.onInkMuted }}>
          Health insurance claims checked against policy rules, with every rupee explained.
        </div>
      </div>
    </div>,
    {
      ...shareImage.size,
      fonts: [{ name: "Geist Pixel", data: await geistPixel, style: "normal", weight: 500 }],
    },
  );
}
