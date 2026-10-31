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

const backdrop = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${scene.viewBox}" width="${shareImage.size.width}" height="${shareImage.size.height}" preserveAspectRatio="xMidYMax slice">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${brand.ink}"/><stop offset="0.62" stop-color="${brand.inkRaised}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.74" cy="0.64" r="0.55" gradientTransform="translate(0.74 0.64) scale(1 0.62) translate(-0.74 -0.64)">
      <stop offset="0" stop-color="${brand.blueBright}" stop-opacity="0.9"/>
      <stop offset="0.45" stop-color="${brand.blue}" stop-opacity="0.55"/>
      <stop offset="1" stop-color="${brand.blue}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="sun" cx="0.76" cy="0.63" r="0.16" gradientTransform="translate(0.76 0.63) scale(1 0.5) translate(-0.76 -0.63)">
      <stop offset="0" stop-color="${brand.signal}" stop-opacity="0.55"/><stop offset="1" stop-color="${brand.signal}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="far" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${brand.inkRaised}"/><stop offset="0.5" stop-color="${brand.ink}"/>
    </linearGradient>
    <linearGradient id="near" x1="0" y1="0.62" x2="0" y2="1">
      <stop offset="0" stop-color="${brand.inkRaised}"/><stop offset="0.35" stop-color="${brand.ink}"/>
    </linearGradient>
    <linearGradient id="ridge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0.45" stop-color="${brand.blueBright}" stop-opacity="0"/>
      <stop offset="0.62" stop-color="${brand.blueBright}" stop-opacity="0.5"/>
      <stop offset="0.78" stop-color="${brand.signal}" stop-opacity="0.9"/>
      <stop offset="1" stop-color="${brand.signal}" stop-opacity="0.35"/>
    </linearGradient>
  </defs>
  <rect width="${scene.width}" height="${scene.height}" fill="url(#sky)"/>
  <rect width="${scene.width}" height="${scene.height}" fill="url(#glow)"/>
  <rect width="${scene.width}" height="${scene.height}" fill="url(#sun)"/>
  <path d="${scene.farDune}" fill="url(#far)"/>
  <path d="${scene.nearDune}" fill="url(#near)"/>
  <path d="${scene.nearRidge}" fill="none" stroke="url(#ridge)" stroke-width="2"/>
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
          <rect width={logoMark.size} height={logoMark.size} rx={logoMark.radius} fill={brand.blue} />
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
