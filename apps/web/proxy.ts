import { type NextRequest, NextResponse } from "next/server"

const CSP_HEADER = "content-security-policy"
const CSP_REPORT_HEADER = "content-security-policy-report-only"
const ACCESS_COOKIE_NAME = "__Host-access_token"
const LOGIN_PATH = "/login"

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
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src ${connect}`,
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
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

export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl
  const signedIn = request.cookies.has(ACCESS_COOKIE_NAME)
  if (!signedIn && pathname !== LOGIN_PATH) {
    const target = new URL(LOGIN_PATH, request.nextUrl)
    if (pathname !== "/") {
      target.searchParams.set("from", `${pathname}${request.nextUrl.search}`)
    }
    return NextResponse.redirect(target, 307)
  }
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/dashboard", request.nextUrl), 307)
  }

  const nonce = Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64")
  const dev = loosePolicyAllowed()
  const policy = directives(nonce, dev)
  const headers = new Headers(request.headers)
  headers.set("x-nonce", nonce)
  headers.set(CSP_HEADER, policy)
  const response = NextResponse.next({ request: { headers } })
  response.headers.set(CSP_HEADER, policy)
  response.headers.set(
    CSP_REPORT_HEADER,
    `require-trusted-types-for 'script'; trusted-types nextjs nextjs#bundler; report-uri /csp-report`,
  )
  return response
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico|healthz|csp-report|client-error).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
}
