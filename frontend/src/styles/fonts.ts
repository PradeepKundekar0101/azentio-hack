import { Geist } from "next/font/google";
import localFont from "next/font/local";

/**
 * Brand typefaces, used by the public pages. The app itself keeps Atkinson Hyperlegible
 * (app/layout.tsx), which suits dense claim data.
 *
 * Geist Pixel (Square) is vendored in ./fonts under the SIL Open Font License (OFL.txt):
 * only this one face is needed, not the whole geist package. The .ttf copy is for the
 * generated share images, which cannot read woff2.
 */
export const geistPixel = localFont({
  src: "./fonts/GeistPixel-Square.woff2",
  variable: "--font-geist-pixel",
  weight: "500",
  display: "swap",
  fallback: ["ui-monospace", "monospace"],
  adjustFontFallback: false,
});

export const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});
