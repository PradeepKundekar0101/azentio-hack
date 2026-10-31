import { geistPixel, geistSans } from "@/styles/fonts";

/** The public landing page: brand type and the ink canvas, whatever theme the app is in. */
export default function WelcomeLayout({ children }: LayoutProps<"/welcome">) {
  return (
    <div
      className={`${geistPixel.variable} ${geistSans.variable} bg-brand-ink font-brand text-brand-on-ink [color-scheme:dark]`}
    >
      {children}
    </div>
  );
}
