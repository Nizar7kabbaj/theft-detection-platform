import type { Metadata, Viewport } from "next"

export const metadata: Metadata = {
  title: "theft detection platform",
  description: "retail theft detection and alert review",
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
