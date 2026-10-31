import { ImageResponse } from "next/og";

import { brand, logoMark } from "@/styles/brand";

// The home-screen icon: the logo mark on a full-bleed tile (iOS applies its own rounding).
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    <div style={{ width: "100%", height: "100%", display: "flex", backgroundColor: brand.blue }}>
      <svg width="180" height="180" viewBox={logoMark.viewBox} fill="none">
        <path
          d={logoMark.form}
          stroke={brand.onInk}
          strokeWidth={logoMark.strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d={logoMark.lines} stroke={brand.onInk} strokeWidth={logoMark.strokeWidth} strokeLinecap="round" />
        <path d={logoMark.drop} fill={brand.onInk} />
      </svg>
    </div>,
    size,
  );
}
