import { dehydrate, HydrationBoundary } from "@tanstack/react-query"
import { Video } from "lucide-react"
import type { Metadata } from "next"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/ui/empty-state"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import { cameraKeys } from "@/features/cameras/api/camera-keys"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { CameraGrid } from "@/features/cameras/components/camera-grid"
import { createServerQueryClient } from "@/lib/api/query-server"

export const metadata: Metadata = { title: "cameras" }
export const dynamic = "force-dynamic"

export default async function CamerasPage() {
  const identity = await fetchIdentity()
  const canRead = identity.permissions.includes("camera:read")

  if (!canRead) {
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

  const queryClient = createServerQueryClient()
  await queryClient.prefetchQuery({
    queryKey: cameraKeys.list(),
    queryFn: () => fetchCameras(),
  })

  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="cameras" description="registered capture sources and their state" />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <CameraGrid />
      </HydrationBoundary>
    </section>
  )
}
