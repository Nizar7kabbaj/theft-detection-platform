import type { ReactNode } from "react"
import { QueryProvider } from "@/providers/query-provider"

export default function DashboardLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <QueryProvider>{children}</QueryProvider>
}
