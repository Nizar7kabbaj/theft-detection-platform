"use client"
import { useQuery } from "@tanstack/react-query"
import { cameraKeys } from "@/features/cameras/api/camera-keys"
import { fetchCamerasClient } from "@/features/cameras/api/cameras-client"
import { useCamerasSocket } from "@/features/cameras/hooks/use-cameras-socket"
import type { Camera } from "@/features/cameras/schemas/camera"

type CameraGrid = {
  cameras: Camera[]
  isPending: boolean
  isError: boolean
}

export function useCameraGrid(): CameraGrid {
  const query = useQuery({
    queryKey: cameraKeys.list(),
    queryFn: ({ signal }) => fetchCamerasClient(signal),
  })

  useCamerasSocket()

  return {
    cameras: query.data ?? [],
    isPending: query.isPending,
    isError: query.isError,
  }
}
