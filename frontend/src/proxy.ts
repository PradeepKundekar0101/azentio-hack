import { NextResponse, type NextRequest } from "next/server";

import { loginPath } from "@/lib/auth/redirect";

export const SESSION_COOKIE = "azentio_session";

/**
 * Optimistic auth check: without a session cookie, app routes redirect to /login before
 * any page renders. The cookie's validity is checked by the backend; an expired cookie
 * gets a 401 from /auth/me and the client-side guard in the app shell redirects then.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const { pathname, search } = request.nextUrl;
  return NextResponse.redirect(new URL(loginPath(`${pathname}${search}`), request.url));
}

export const config = {
  // Everything except the login page, API/health rewrites, Next internals and static files.
  matcher: ["/((?!login|api/|health|_next/|favicon\\.ico|.*\\.[\\w]+$).*)"],
};
