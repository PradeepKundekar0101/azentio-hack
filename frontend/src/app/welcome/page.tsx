import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { LogoMark, PRODUCT_NAME } from "@/components/brand";
import { LANDING_PATH, LOGIN_PATH } from "@/lib/auth/redirect";

import { Backdrop } from "./backdrop";

export const metadata: Metadata = {
  title: { absolute: `${PRODUCT_NAME} | Find the leakage in every claim` },
};

const FACTS = [
  { title: "Policy rules", body: "Every claim is checked against the rules of its own policy." },
  { title: "Duplicates", body: "Repeated claims and bills are detected and flagged." },
  { title: "Leakage in rupees", body: "Each alert states the amount at stake and the reason." },
  { title: "No AI in the maths", body: "Amounts come from fixed rules. AI only reads documents." },
] as const;

const focusRing =
  "outline-none focus-visible:ring-2 focus-visible:ring-brand-on-ink focus-visible:ring-offset-2 focus-visible:ring-offset-brand-ink";

const glass = "border border-brand-on-ink/10 bg-brand-ink/50 backdrop-blur-md";

export default function WelcomePage() {
  return (
    <div className="relative isolate flex min-h-svh flex-col overflow-hidden">
      <Backdrop />

      <header className="flex items-center justify-between gap-4 px-5 pt-5 sm:px-10 sm:pt-6 lg:px-20">
        <Link href={LANDING_PATH} className={`flex h-11 items-center gap-2.5 rounded-md px-3 ${glass} ${focusRing}`}>
          <LogoMark className="size-6" />
          <span className="text-[15px] font-medium tracking-[-0.01em]">{PRODUCT_NAME}</span>
        </Link>
        <nav aria-label="Account">
          <Link
            href={LOGIN_PATH}
            className={`flex h-11 items-center rounded-md px-4 text-[15px] text-brand-on-ink/85 transition-colors duration-150 hover:bg-brand-ink/70 hover:text-brand-on-ink ${glass} ${focusRing}`}
          >
            Sign in
          </Link>
        </nav>
      </header>

      <main className="mt-auto px-5 pt-20 pb-10 sm:px-10 sm:pb-12 lg:px-20 lg:pb-14">
        <h1 className="max-w-[16ch] animate-in font-pixel text-[clamp(2.375rem,min(5.4vw,9.5svh),5rem)] leading-[1.02] font-medium text-balance uppercase delay-150 duration-700 fill-mode-both fade-in slide-in-from-bottom-3">
          Find the leakage in every claim
        </h1>
        <p className="mt-6 max-w-[38rem] animate-in text-[17px] leading-[1.6] text-brand-on-ink-muted delay-300 duration-700 fill-mode-both fade-in slide-in-from-bottom-2 sm:text-[19px]">
          {PRODUCT_NAME} checks each health insurance claim against its policy, flags duplicates and puts a rupee
          figure on every problem, with the rule and record behind it.
        </p>
        <Link
          href={LOGIN_PATH}
          className={`group mt-9 inline-flex h-12 animate-in items-center gap-2 rounded-md bg-brand-on-ink px-5 text-[15px] font-medium text-brand-ink transition-colors delay-500 duration-700 fill-mode-both fade-in hover:bg-brand-on-ink/90 ${focusRing}`}
        >
          Sign in to the dashboard
          <ArrowRight
            aria-hidden="true"
            className="size-4 transition-transform duration-150 group-hover:translate-x-0.5"
          />
        </Link>
      </main>

      <section aria-label="What it checks" className="border-t border-brand-on-ink/10 bg-brand-ink/75 backdrop-blur-sm">
        <ul className="grid grid-cols-2 lg:grid-cols-4">
          {FACTS.map((fact, i) => (
            <li
              key={fact.title}
              className={`border-brand-on-ink/10 px-5 py-5 sm:px-10 sm:py-6 lg:px-8 lg:first:pl-20 ${i % 2 === 0 ? "border-r" : ""} ${i < 2 ? "border-b lg:border-b-0" : ""} lg:border-r lg:last:border-r-0`}
            >
              <p className="font-pixel text-[13px] tracking-[0.04em] uppercase">{fact.title}</p>
              <p className="mt-1.5 text-[14px] leading-[1.5] text-brand-on-ink-muted">{fact.body}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
