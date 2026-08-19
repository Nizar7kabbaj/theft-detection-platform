"use client"
import { useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { cameraKeys } from "@/features/cameras/api/camera-keys"
import {
  type Camera,
  cameraSchema,
  healthEventSchema,
  healthEventToView,
} from "@/features/cameras/schemas/camera"
import type { StreamEnvelope } from "@/lib/websocket/envelope"
import { useStream } from "@/lib/websocket/use-stream"

export function useCamerasSocket(): void {
  const queryClient = useQueryClient()

  const onEvent = useCallback(
    (envelope: StreamEnvelope) => {
      const key = cameraKeys.list()

      if (envelope.event === "created") {
        const parsed = cameraSchema.safeParse(envelope.data)
        if (!parsed.success) {
          return
        }
        const camera = parsed.data
        queryClient.setQueryData<Camera[]>(key, (current) => {
          if (current === undefined) {
            return current
          }
          if (current.some((item) => item._id === camera._id)) {
            return current.map((item) => (item._id === camera._id ? camera : item))
          }
          return [...current, camera]
        })
        return
      }

      if (envelope.event === "deleted") {
        const parsed = cameraSchema.safeParse(envelope.data)
        if (!parsed.success) {
          return
        }
        const camera = parsed.data
        queryClient.setQueryData<Camera[]>(key, (current) => {
          if (current === undefined) {
            return current
          }
          return current.filter((item) => item._id !== camera._id)
        })
        return
      }

      if (envelope.event === "health") {
        const parsed = healthEventSchema.safeParse(envelope.data)
        if (!parsed.success) {
          return
        }
        const event = parsed.data
        const view = healthEventToView(event)
        queryClient.setQueryData<Camera[]>(key, (current) => {
          if (current === undefined) {
            return current
          }
          let seen = false
          const next = current.map((item) => {
            if (item.camera_id !== event.camera_id) {
              return item
            }
            seen = true
            return { ...item, health: view }
          })
          return seen ? next : current
        })
      }
    },
    [queryClient],
  )

  useStream("cameras", onEvent)
}
