import type { Metadata, Viewport } from "next";
import { Atkinson_Hyperlegible_Mono, Atkinson_Hyperlegible_Next } from "next/font/google";

import { PRODUCT_NAME } from "@/components/brand";
import { Providers } from "@/components/providers";

import "./globals.css";

// Atkinson Hyperlegible was drawn for the Braille Institute to keep similar glyphs
// (1/l/I, 0/O, 5/S, 8/B) distinct: the property that matters most when people read
// claim numbers, invoice references and amounts all day.
const atkinson = Atkinson_Hyperlegible_Next({
  variable: "--font-atkinson",
  subsets: ["latin", "latin-ext"],
  display: "swap",
  // Next has no metrics to size-match a fallback for this family.
  adjustFontFallback: false,
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
});

const atkinsonMono = Atkinson_Hyperlegible_Mono({
  variable: "--font-atkinson-mono",
  subsets: ["latin"],
  display: "swap",
  adjustFontFallback: false,
  fallback: ["ui-monospace", "monospace"],
});

const DESCRIPTION =
  "Validate health insurance claims against policy rules, find duplicates and explain every rupee of leakage.";

export const metadata: Metadata = {
  // Share images need absolute URLs. SITE_URL is the deployed origin (App Platform's APP_URL).
  metadataBase: new URL(process.env.SITE_URL || "http://localhost:3000"),
  title: { default: PRODUCT_NAME, template: `%s | ${PRODUCT_NAME}` },
  description: DESCRIPTION,
  applicationName: PRODUCT_NAME,
  openGraph: { type: "website", siteName: PRODUCT_NAME, title: PRODUCT_NAME, description: DESCRIPTION },
  twitter: { card: "summary_large_image", title: PRODUCT_NAME, description: DESCRIPTION },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f2ec" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0a09" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en-IN"
      className={`${atkinson.variable} ${atkinsonMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
