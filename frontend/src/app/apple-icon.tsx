import { ImageResponse } from "next/og";

import { brand, logoMark } from "@/styles/brand";

// The home-screen icon: the logo mark on a full-bleed tile (iOS applies its own rounding).
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    <div style={{ width: "100%", height: "100%", display: "flex", backgroundColor: brand.ink }}>
      <svg width="180" height="180" viewBox={logoMark.viewBox}>
        <path d={logoMark.lines} fill={brand.onInk} />
        <path d={logoMark.leak} fill={brand.signal} />
      </svg>
    </div>,
    size,
  );
}
