import type { Metadata, Viewport } from "next"
import "./globals.css"
import { GeistSans } from "geist/font/sans"
import { headers } from "next/headers"

export const metadata: Metadata = {
  title: "theft detection platform",
  description: "retail theft detection and alert review",
  robots: { index: false, follow: false },
}
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
}
export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const nonce = (await headers()).get("x-nonce") ?? undefined
  return (
    <html lang="en" className={GeistSans.variable}>
      <body className="font-sans" nonce={nonce}>
        {children}
      </body>
    </html>
  )
}
