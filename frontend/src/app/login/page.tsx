import type { Metadata } from "next";

import { PRODUCT_NAME, Wordmark } from "@/components/brand";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div className="canvas-glow relative isolate flex min-h-dvh flex-col bg-canvas px-4 py-6 sm:px-6">
      {/* The brand mesh, faint, behind the card: the same light the landing page is lit by. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[52vh] bg-[radial-gradient(60%_70%_at_50%_0%,color-mix(in_oklch,var(--brand-mesh-sky)_55%,transparent),transparent_70%),radial-gradient(40%_50%_at_80%_10%,color-mix(in_oklch,var(--brand-mesh-ember)_28%,transparent),transparent_70%)] opacity-70 dark:opacity-90"
      />
      <header className="flex h-8 items-center">
        <Wordmark />
      </header>
      {/* Anchored near the top rather than centred, so an inline error grows the card
          downwards without moving the heading and fields. */}
      <main className="flex flex-1 items-start justify-center pt-[clamp(2.5rem,14vh,8rem)] pb-10">
        <div className="page-enter w-full max-w-[24rem] rounded-2xl bg-card px-6 py-7 shadow-pop sm:px-8 sm:py-8">
          <h1 className="text-2xl leading-8 font-semibold tracking-[-0.015em]">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">Use the team account for {PRODUCT_NAME}.</p>
          <LoginForm />
        </div>
      </main>
    </div>
  );
}
