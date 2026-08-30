import { type NextRequest, NextResponse } from "next/server"
const CSP_HEADER = "content-security-policy"
const CSP_REPORT_HEADER = "content-security-policy-report-only"
const ACCESS_COOKIE_NAME = "__Host-access_token"
const REFRESH_COOKIE_NAME = "__Host-refresh_token"
const CSRF_COOKIE_NAME = "__Host-csrf"
const CSRF_HEADER_NAME = "X-CSRF-Token"
const LOGIN_PATH = "/login"
const REFRESH_PATH = "/auth/refresh"
const REFRESH_TIMEOUT_MS = 5_000
function directives(nonce: string, dev: boolean): string {
  const script = dev
    ? `'nonce-${nonce}' 'strict-dynamic' 'unsafe-eval'`
    : `'nonce-${nonce}' 'strict-dynamic'`
  const styleElem = dev ? `'self' 'unsafe-inline'` : `'self' 'nonce-${nonce}'`
  const connect = dev ? "'self' ws: wss:" : "'self'"
  return [
    "default-src 'none'",
    `script-src ${script}`,
    `style-src-elem ${styleElem}`,
    "style-src-attr 'none'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src ${connect}`,
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
    "report-to csp-endpoint",
    "report-uri /csp-report",
    "upgrade-insecure-requests",
  ].join("; ")
}
let looseNoticeEmitted = false
function loosePolicyAllowed(): boolean {
  if (process.env.NODE_ENV === "production") {
    return false
  }
  if (process.env.NEXT_PUBLIC_ALLOW_DEV_CSP !== "1") {
    return false
  }
  if (!looseNoticeEmitted) {
    looseNoticeEmitted = true
    process.stdout.write(
      `${JSON.stringify({ event: "csp_dev_policy_active", at: new Date().toISOString() })}\n`,
    )
  }
  return true
}
function noteAuthRedirect(request: NextRequest, reason: string): void {
  process.stdout.write(
    `${JSON.stringify({
      event: "session_redirect_to_login",
      path: request.nextUrl.pathname,
      reason,
      cookies: request.cookies.getAll().map((entry) => entry.name),
      secFetchSite: request.headers.get("sec-fetch-site"),
      secFetchMode: request.headers.get("sec-fetch-mode"),
      secFetchDest: request.headers.get("sec-fetch-dest"),
      purpose: request.headers.get("next-router-prefetch"),
      at: new Date().toISOString(),
    })}\n`,
  )
}
function authBaseUrl(): string | null {
  const configured = process.env.AUTH_BASE_URL
  if (configured === undefined || configured === "") {
    return null
  }
  return configured.replace(/\/+$/, "")
}
function cookieValueOf(setCookie: string, name: string): string | null {
  const pair = setCookie.split(";", 1)[0]
  if (pair === undefined) {
    return null
  }
  const separator = pair.indexOf("=")
  if (separator === -1 || pair.slice(0, separator).trim() !== name) {
    return null
  }
  const value = pair.slice(separator + 1).trim()
  return value === "" ? null : value
}
type RefreshOutcome =
  | { ok: true; setCookies: readonly string[]; accessToken: string }
  | { ok: false; reason: string }
async function renewSession(request: NextRequest): Promise<RefreshOutcome> {
  const base = authBaseUrl()
  if (base === null) {
    return { ok: false, reason: "no-base-url" }
  }
  const refreshToken = request.cookies.get(REFRESH_COOKIE_NAME)?.value
  if (refreshToken === undefined) {
    return { ok: false, reason: "no-refresh-cookie" }
  }
  const csrfToken = request.cookies.get(CSRF_COOKIE_NAME)?.value
  if (csrfToken === undefined) {
    return { ok: false, reason: "no-csrf-cookie" }
  }
  let response: Response
  try {
    response = await fetch(`${base}${REFRESH_PATH}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        [CSRF_HEADER_NAME]: csrfToken,
        Cookie: `${REFRESH_COOKIE_NAME}=${refreshToken}; ${CSRF_COOKIE_NAME}=${csrfToken}`,
      },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(REFRESH_TIMEOUT_MS),
    })
  } catch (cause) {
    const name = cause instanceof Error ? cause.name : "unknown"
    return { ok: false, reason: `fetch-threw-${name}` }
  }
  if (!response.ok) {
    return { ok: false, reason: `status-${response.status}` }
  }
  const setCookies = response.headers.getSetCookie()
  for (const entry of setCookies) {
    const accessToken = cookieValueOf(entry, ACCESS_COOKIE_NAME)
    if (accessToken !== null) {
      return { ok: true, setCookies, accessToken }
    }
  }
  return { ok: false, reason: `no-access-in-${setCookies.length}-cookies` }
}
function rewriteCookieHeader(request: NextRequest, accessToken: string): string {
  const pairs = request.cookies
    .getAll()
    .filter((entry) => entry.name !== ACCESS_COOKIE_NAME)
    .map((entry) => `${entry.name}=${entry.value}`)
  pairs.push(`${ACCESS_COOKIE_NAME}=${accessToken}`)
  return pairs.join("; ")
}
function loginRedirect(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl
  const target = new URL(LOGIN_PATH, request.nextUrl)
  if (pathname !== "/") {
    target.searchParams.set("from", `${pathname}${request.nextUrl.search}`)
  }
  return NextResponse.redirect(target, 307)
}
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl
  const hasAccess = request.cookies.has(ACCESS_COOKIE_NAME)
  const hasRefresh = request.cookies.has(REFRESH_COOKIE_NAME)
  let renewed: RefreshOutcome | null = null
  if (!hasAccess && hasRefresh && pathname !== LOGIN_PATH) {
    renewed = await renewSession(request)
    if (!renewed.ok) {
      noteAuthRedirect(request, renewed.reason)
      return loginRedirect(request)
    }
  }
  if (!hasAccess && renewed === null && pathname !== LOGIN_PATH) {
    noteAuthRedirect(request, "no-access-cookie-no-refresh-cookie")
    return loginRedirect(request)
  }
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/dashboard", request.nextUrl), 307)
  }
  const nonce = Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64")
  const dev = loosePolicyAllowed()
  const policy = directives(nonce, dev)
  const headers = new Headers(request.headers)
  headers.set("x-nonce", nonce)
  headers.set("x-pathname", `${pathname}${request.nextUrl.search}`)
  headers.set(CSP_HEADER, policy)
  if (renewed?.ok) {
    headers.set("cookie", rewriteCookieHeader(request, renewed.accessToken))
  }
  const response = NextResponse.next({ request: { headers } })
  response.headers.set(CSP_HEADER, policy)
  response.headers.set("reporting-endpoints", `csp-endpoint="/csp-report"`)
  response.headers.set(
    CSP_REPORT_HEADER,
    `require-trusted-types-for 'script'; trusted-types nextjs nextjs#bundler; report-to csp-endpoint; report-uri /csp-report`,
  )
  if (renewed?.ok) {
    for (const entry of renewed.setCookies) {
      response.headers.append("set-cookie", entry)
    }
  }
  return response
}
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|healthz|csp-report|client-error).*)"],
}
