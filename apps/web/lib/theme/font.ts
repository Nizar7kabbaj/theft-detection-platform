import localFont from "next/font/local"
export const inter = localFont({
  src: "../../app/fonts/inter-latin-variable.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--font-inter",
  preload: true,
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
})
