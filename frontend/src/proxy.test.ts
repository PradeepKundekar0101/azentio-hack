import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { config, proxy, SESSION_COOKIE } from "./proxy";

const ORIGIN = "http://localhost:3000";

function run(path: string, { signedIn = false } = {}) {
  const headers = signedIn ? { cookie: `${SESSION_COOKIE}=token` } : undefined;
  return proxy(new NextRequest(`${ORIGIN}${path}`, { headers }));
}

describe("proxy", () => {
  it("sends signed-out visitors at the root to the landing page", () => {
    const response = run("/");
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(`${ORIGIN}/welcome`);
  });

  it("sends signed-out visitors on an app route to sign in, returning there afterwards", () => {
    const response = run("/alerts?severity=high");
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(`${ORIGIN}/login?next=%2Falerts%3Fseverity%3Dhigh`);
  });

  it.each(["/", "/alerts"])("lets a signed-in user through to %s", (path) => {
    const response = run(path, { signedIn: true });
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});

describe("proxy matcher", () => {
  // Next compiles the matcher with path-to-regexp; anchoring the raw pattern is equivalent for these paths.
  const matcher = new RegExp(`^${config.matcher[0]}$`);

  it.each(["/", "/alerts", "/imports", "/documents/42"])("guards the app route %s", (path) => {
    expect(matcher.test(path)).toBe(true);
  });

  it.each([
    "/login",
    "/welcome",
    "/opengraph-image",
    "/twitter-image",
    "/apple-icon",
    "/icon.svg",
    "/favicon.ico",
    "/api/auth/me",
    "/health",
    "/_next/static/chunk.js",
  ])("leaves the public path %s alone", (path) => {
    expect(matcher.test(path)).toBe(false);
  });
});
