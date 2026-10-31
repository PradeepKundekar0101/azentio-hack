/** Where users land after sign-in when no `next` is given. */
export const HOME_PATH = "/";
export const LOGIN_PATH = "/login";

// A placeholder origin for parsing relative paths. `.invalid` is reserved and never resolves.
const BASE = "http://next.invalid";

/**
 * Accepts only same-site relative paths for post-login redirects; anything else gives
 * HOME_PATH. The path is parsed the way the browser would parse it, so tricks such as
 * `//evil.com`, `/\evil.com` or a tab inside `//` cannot turn it into another origin.
 */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/")) return HOME_PATH;
  let url: URL;
  try {
    url = new URL(next, BASE);
  } catch {
    return HOME_PATH;
  }
  if (url.origin !== BASE) return HOME_PATH;
  if (url.pathname === LOGIN_PATH || url.pathname.startsWith(`${LOGIN_PATH}/`)) return HOME_PATH;
  return `${url.pathname}${url.search}${url.hash}`;
}

/** The login URL that returns to `next` afterwards (`/login?next=%2Falerts`). */
export function loginPath(next?: string | null): string {
  const target = safeNextPath(next);
  return target === HOME_PATH ? LOGIN_PATH : `${LOGIN_PATH}?next=${encodeURIComponent(target)}`;
}
