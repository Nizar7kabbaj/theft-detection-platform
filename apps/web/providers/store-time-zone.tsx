"use client"

import type { ReactNode } from "react"
import { setStoreTimeZone } from "@/lib/time/zone"

export function StoreTimeZone({ zone, children }: { zone: string; children: ReactNode }) {
  setStoreTimeZone(zone)
  return children
}
