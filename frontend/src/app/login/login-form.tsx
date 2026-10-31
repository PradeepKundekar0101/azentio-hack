"use client";

import { CircleAlert, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorMessage } from "@/lib/api/errors";
import { useLogin } from "@/lib/auth/hooks";
import { safeNextPath } from "@/lib/auth/redirect";

export function LoginForm() {
  const router = useRouter();

  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const errorId = useId();

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
    </form>
  );
}
