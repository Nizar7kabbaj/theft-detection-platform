"use client"
import dynamic from "next/dynamic"

const SURFACE_CLASS = "aspect-[16/10] w-full animate-pulse rounded-lg bg-muted"

const Console = dynamic(
  () => import("@/features/floorplan/components/floor-console").then((m) => m.FloorConsole),
  {
    ssr: false,
    loading: () => <div className={SURFACE_CLASS} />,
  },
)

export function FloorConsoleLazy() {
  return <Console />
}
