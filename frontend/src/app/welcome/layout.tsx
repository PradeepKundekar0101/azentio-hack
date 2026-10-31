import { Geist } from "next/font/google";
import localFont from "next/font/local";

// Geist Pixel (Square) is vendored here under the SIL Open Font License (fonts/OFL.txt):
// only this one 28 KB face is needed, not the whole family package.
const geistPixel = localFont({
  src: "./fonts/GeistPixel-Square.woff2",
  variable: "--font-geist-pixel",
  weight: "500",
  display: "swap",
  fallback: ["ui-monospace", "monospace"],
  adjustFontFallback: false,
});

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

/**
 * The public landing page has its own type: Geist Pixel for display lines and Geist Sans
 * for running text. The app keeps Atkinson Hyperlegible, which suits dense claim data.
 */
export default function WelcomeLayout({ children }: LayoutProps<"/welcome">) {
  return (
    <div
      className={`${geistPixel.variable} ${geistSans.variable} bg-[#0b0d14] font-[family-name:var(--font-geist-sans)] text-white [color-scheme:dark]`}
    >
      {children}
    </div>
  );
}
