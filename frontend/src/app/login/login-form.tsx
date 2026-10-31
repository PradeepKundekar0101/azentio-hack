"use client";

import { CircleAlert, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorMessage } from "@/lib/api/errors";
import { type DemoAccount, useDemoAccounts, useLogin } from "@/lib/auth/hooks";
import { ROLE_DESCRIPTIONS, roleLabel } from "@/lib/auth/permissions";
import { safeNextPath } from "@/lib/auth/redirect";

export function LoginForm() {
  const router = useRouter();

  const login = useLogin();
  const demo = useDemoAccounts();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const errorId = useId();

  const fill = (account: DemoAccount) => {
    login.reset();
    setUsername(account.username);
    setPassword(account.password);
  };

  // Next keeps visited routes alive (hidden) for back/forward. When this page is hidden
  // after a successful sign-in, clear it so a later visit shows a fresh form.
  const { reset } = login;
  useEffect(
    () => () => {
      reset();
      setPassword("");
    },
    [reset],
  );

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Read `next` at submit time rather than with useSearchParams, so the form needs no
    // Suspense boundary and is part of the prerendered page (no layout shift on load).
    const next = safeNextPath(new URLSearchParams(window.location.search).get("next"));
    login.mutate({ username: username.trim(), password }, { onSuccess: () => router.replace(next) });
  };

  const busy = login.isPending || login.isSuccess;
  const error = login.isError ? getErrorMessage(login.error) : null;
  const describedBy = error ? errorId : undefined;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="username">Username</Label>
        <Input
          id="username"
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          required
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className="h-9"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className="h-9"
        />
      </div>

      {error && (
        <Alert variant="destructive" id={errorId} aria-live="polite">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" size="lg" className="h-9 w-full" disabled={busy}>
        {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
        {busy ? "Signing in" : "Sign in"}
      </Button>

      {demo.data && demo.data.length > 0 && (
        <fieldset className="mt-2 min-w-0 border-t pt-4" disabled={busy}>
          <legend className="sr-only">Demo accounts</legend>
          <p className="text-xs font-medium text-muted-foreground">Demo accounts: pick one to fill the form</p>
          <ul className="mt-2 grid gap-1.5">
            {demo.data.map((account) => (
              <li key={account.username}>
                <button
                  type="button"
                  onClick={() => fill(account)}
                  aria-pressed={username === account.username}
                  className="flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring aria-pressed:border-primary/40 aria-pressed:bg-primary/5"
                >
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium">{roleLabel(account.role)}</span>
                    <span className="block truncate text-xs text-muted-foreground">{ROLE_DESCRIPTIONS[account.role]}</span>
                  </span>
                  <span className="num shrink-0 text-xs text-muted-foreground">{account.username}</span>
                </button>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
    </form>
  );
}
