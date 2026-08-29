import { dehydrate, HydrationBoundary } from "@tanstack/react-query"
import { Video } from "lucide-react"
import type { Metadata } from "next"
import { cookies } from "next/headers"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/ui/empty-state"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import {
  CAMERA_COOKIE_NAME,
  FLEET_FILTER_COOKIE_NAME,
  parseCameraId,
  parseFleetFilter,
} from "@/features/cameras/api/camera-cookie"
import { cameraKeys } from "@/features/cameras/api/camera-keys"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { CameraConsole } from "@/features/cameras/components/camera-console"
import { createServerQueryClient } from "@/lib/api/query-server"
export const metadata: Metadata = { title: "cameras" }
export const dynamic = "force-dynamic"
export default async function CamerasPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const [identity, params, store] = await Promise.all([fetchIdentity(), searchParams, cookies()])
  if (!identity.permissions.includes("camera:read")) {
    return (
      <section className="flex flex-1 flex-col gap-5">
        <PageHeader title="cameras" description="registered capture sources and their state" />
        <EmptyState
          icon={Video}
          title="not authorized"
          description="your account does not have permission to view cameras"
        />
      </section>
    )
  }
  const requested = params.id
  const fromUrl = parseCameraId(typeof requested === "string" ? requested : null)
  const fromCookie = parseCameraId(store.get(CAMERA_COOKIE_NAME)?.value ?? null)
  const initialFilter = parseFleetFilter(store.get(FLEET_FILTER_COOKIE_NAME)?.value ?? null)
  const queryClient = createServerQueryClient()
  await queryClient.prefetchQuery({
    queryKey: cameraKeys.list(),
    queryFn: () => fetchCameras(),
  })
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="cameras" description="registered capture sources and their state" />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <CameraConsole initialCameraId={fromUrl ?? fromCookie} initialFilter={initialFilter} />
      </HydrationBoundary>
    </section>
  )
}
