import type { Metadata, Viewport } from "next"
import "./globals.css"
import { GeistSans } from "geist/font/sans"
import { cookies, headers } from "next/headers"
import { DEFAULT_THEME, parseTheme, THEME_COOKIE_NAME } from "@/lib/theme/theme-cookie"

export const metadata: Metadata = {
  title: "theft detection platform",
  description: "retail theft detection and alert review",
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
}

const THEME_SCRIPT = `(function(){try{var m=document.cookie.match(/(?:^|; )${THEME_COOKIE_NAME}=([^;]*)/);var t=m?decodeURIComponent(m[1]):"${DEFAULT_THEME}";if(t==="system"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.classList.toggle("dark",t==="dark")}catch(e){document.documentElement.classList.add("dark")}})()`

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const [headerList, cookieStore] = await Promise.all([headers(), cookies()])
  const nonce = headerList.get("x-nonce") ?? undefined
  const theme = parseTheme(cookieStore.get(THEME_COOKIE_NAME)?.value)
  const serverDark = theme !== "light"
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={serverDark ? `dark ${GeistSans.variable}` : GeistSans.variable}
    >
      <body className="font-sans">
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        {children}
      </body>
    </html>
  )
}
