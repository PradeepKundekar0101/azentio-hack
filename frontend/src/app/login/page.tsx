import type { Metadata } from "next";
import Link from "next/link";

import { LogoMark, PRODUCT_NAME } from "@/components/brand";
import { LANDING_PATH } from "@/lib/auth/redirect";
import { geistPixel, geistSans } from "@/styles/fonts";

import { Backdrop } from "../welcome/backdrop";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

const focusRing =
  "outline-none focus-visible:ring-2 focus-visible:ring-brand-on-ink focus-visible:ring-offset-2 focus-visible:ring-offset-brand-ink";

/**
 * The door between the public page and the portal: the same mesh backdrop, header and
 * type as the landing page, with the sign-in card (app type and tokens) floating on it,
 * so the step from one to the other feels like one site.
 */
export default function LoginPage() {
  return (
    <div
      className={`${geistPixel.variable} ${geistSans.variable} relative isolate flex min-h-dvh flex-col bg-brand-ink px-5 pt-5 pb-10 font-brand text-brand-on-ink [color-scheme:dark] sm:px-10 sm:pt-6 lg:px-20`}
    >
      {/* Fixed, still and on its own layer: a moving blurred SVG repaints on every scroll frame. */}
      <Backdrop className="fixed transform-gpu [contain:strict] [&_*]:!animate-none" />
      <header className="flex h-11 items-center">
        <Link
          href={LANDING_PATH}
          className={`flex h-11 items-center gap-2.5 rounded-md border border-brand-on-ink/10 bg-brand-ink/50 px-3 backdrop-blur-md ${focusRing}`}
        >
          <LogoMark className="size-6" />
          <span className="text-[15px] font-medium tracking-[-0.01em]">{PRODUCT_NAME}</span>
        </Link>
      </header>
      {/* Anchored near the top rather than centred, so an inline error grows the card
          downwards without moving the heading and fields. */}
      <main className="flex flex-1 items-start justify-center pt-[clamp(2.5rem,14vh,8rem)]">
        <div className="page-enter w-full max-w-[24rem] md:max-w-[50rem]">
          <p className="mb-4 text-center font-pixel text-[13px] tracking-[0.08em] text-brand-on-ink-muted uppercase">
            Sign in to the dashboard
          </p>
          <div className="flex flex-col items-center gap-5 md:flex-row md:items-start md:justify-center">
            <LoginForm
              heading={
                <div>
                  <h1 className="text-2xl leading-8 font-semibold tracking-[-0.015em]">Sign in</h1>
                  <p className="mt-1 text-sm text-muted-foreground">Use the team account for {PRODUCT_NAME}.</p>
                </div>
              }
            />
          </div>
        </div>
      </main>
    </div>
  );
}
