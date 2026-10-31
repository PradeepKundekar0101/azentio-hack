import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { LogoMark, PRODUCT_NAME } from "@/components/brand";
import { LOGIN_PATH } from "@/lib/auth/redirect";

import ridge from "./ridge.jpg";

export const metadata: Metadata = {
  title: { absolute: `${PRODUCT_NAME} | Find the leakage in every claim` },
};

const FACTS = [
  { title: "Policy rules", body: "Every claim is checked against the rules of its own policy." },
  { title: "Duplicates", body: "Repeated claims and bills are detected and flagged." },
  { title: "Leakage in rupees", body: "Each alert states the amount at stake and the reason." },
  { title: "No AI in the maths", body: "Amounts come from fixed rules. AI only reads documents." },
] as const;

// Film grain over the photograph: a tiny SVG noise tile, so the texture costs no request.
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

const focusRing =
  "outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[#0b0d14]";

export default function WelcomePage() {
  return (
    <div className="relative isolate flex min-h-svh flex-col overflow-hidden">
      <Image
        src={ridge}
        alt=""
        fill
        preload
        sizes="100vw"
        placeholder="blur"
        className="-z-20 animate-in object-cover object-[62%_center] duration-[1400ms] ease-out fade-in zoom-in-105"
      />
      {/* Darken the lower left, where the text sits, and fade into the page colour at the bottom. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-[linear-gradient(to_top,#0b0d14_0%,rgb(11_13_20/0.88)_22%,rgb(11_13_20/0.2)_58%,rgb(11_13_20/0.35)_100%),linear-gradient(to_right,rgb(11_13_20/0.55),transparent_65%)]"
      />
      {/* On narrow screens the crop is mostly bright sky, so the headline needs a deeper scrim. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-[linear-gradient(to_top,rgb(11_13_20/0.6)_35%,rgb(11_13_20/0.45)_65%,transparent_90%)] lg:hidden"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 opacity-[0.22] mix-blend-overlay"
        style={{ backgroundImage: GRAIN }}
      />

      <header className="flex items-center justify-between gap-4 px-5 pt-5 sm:px-10 sm:pt-6 lg:px-20">
        <Link
          href="/welcome"
          className={`flex h-11 items-center gap-2.5 rounded-md border border-white/10 bg-black/45 px-3 backdrop-blur-md ${focusRing}`}
        >
          <LogoMark className="size-5" />
          <span className="text-[15px] font-medium tracking-[-0.01em]">{PRODUCT_NAME}</span>
        </Link>
        <nav aria-label="Account">
          <Link
            href={LOGIN_PATH}
            className={`flex h-11 items-center rounded-md border border-white/10 bg-black/45 px-4 text-[15px] text-white/85 backdrop-blur-md transition-colors duration-150 hover:bg-black/60 hover:text-white ${focusRing}`}
          >
            Sign in
          </Link>
        </nav>
      </header>

      <main className="mt-auto px-5 pt-28 pb-10 sm:px-10 sm:pb-12 lg:px-20 lg:pb-14">
        <h1 className="max-w-[16ch] animate-in font-[family-name:var(--font-geist-pixel)] text-[clamp(2.375rem,5.4vw,5rem)] leading-[1.02] font-medium text-balance uppercase delay-150 duration-700 fill-mode-both fade-in slide-in-from-bottom-3">
          Find the leakage in every claim
        </h1>
        <p className="mt-6 max-w-[38rem] animate-in text-[17px] leading-[1.6] text-white/75 delay-300 duration-700 fill-mode-both fade-in slide-in-from-bottom-2 sm:text-[19px]">
          {PRODUCT_NAME} checks each health insurance claim against its policy, flags duplicates and puts a rupee
          figure on every problem, with the rule and record behind it.
        </p>
        <Link
          href={LOGIN_PATH}
          className={`group mt-9 inline-flex h-12 animate-in items-center gap-2 rounded-md bg-white px-5 text-[15px] font-medium text-[#0b0d14] transition-colors delay-500 duration-700 fill-mode-both fade-in hover:bg-white/90 ${focusRing}`}
        >
          Sign in to the dashboard
          <ArrowRight
            aria-hidden="true"
            className="size-4 transition-transform duration-150 group-hover:translate-x-0.5"
          />
        </Link>
      </main>

      <section aria-label="What it checks" className="border-t border-white/10 bg-[#0b0d14]/70 backdrop-blur-sm">
        <ul className="grid grid-cols-2 lg:grid-cols-4">
          {FACTS.map((fact, i) => (
            <li
              key={fact.title}
              className={`border-white/10 px-5 py-5 sm:px-10 sm:py-6 lg:px-8 lg:first:pl-20 ${i % 2 === 0 ? "border-r" : ""} ${i < 2 ? "border-b lg:border-b-0" : ""} lg:border-r lg:last:border-r-0`}
            >
              <p className="font-[family-name:var(--font-geist-pixel)] text-[13px] tracking-[0.04em] text-white uppercase">
                {fact.title}
              </p>
              <p className="mt-1.5 text-[14px] leading-[1.5] text-white/60">{fact.body}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
