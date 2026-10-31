import type { Metadata } from "next";

import { PRODUCT_NAME, Wordmark } from "@/components/brand";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas px-4 py-6 sm:px-6">
      <header className="flex h-8 items-center">
        <Wordmark />
      </header>
      {/* Anchored near the top rather than centred, so an inline error grows the card
          downwards without moving the heading and fields. */}
      <main className="flex flex-1 items-start justify-center pt-[clamp(2.5rem,14vh,8rem)] pb-10">
        <div className="w-full max-w-[24rem] rounded-xl border bg-card px-6 py-7 shadow-xs sm:px-8 sm:py-8">
          <h1 className="text-2xl leading-8 font-semibold tracking-[-0.015em]">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">Use the team account for {PRODUCT_NAME}.</p>
          <LoginForm />
        </div>
      </main>
    </div>
  );
}
