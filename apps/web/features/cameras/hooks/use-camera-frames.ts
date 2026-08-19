"use client"
import { useEffect, useRef, useState } from "react"
import {
  type FrameHealth,
  type FrameStatus,
  openFrameSocket,
} from "@/features/cameras/lib/frame-socket"

type FrameView = {
  src: string | null
  status: FrameStatus
  health: FrameHealth | null
}

export function useCameraFrames(cameraId: string): FrameView {
  const [src, setSrc] = useState<string | null>(null)
  const [status, setStatus] = useState<FrameStatus>("connecting")
  const [health, setHealth] = useState<FrameHealth | null>(null)
  const currentUrl = useRef<string | null>(null)

  useEffect(() => {
    const revoke = (): void => {
      if (currentUrl.current !== null) {
        URL.revokeObjectURL(currentUrl.current)
        currentUrl.current = null
      }
    }

    const close = openFrameSocket(cameraId, {
      onFrame: (blob) => {
        const url = URL.createObjectURL(blob)
        const previous = currentUrl.current
        currentUrl.current = url
        setSrc(url)
        if (previous !== null) {
          URL.revokeObjectURL(previous)
        }
      },
      onHealth: setHealth,
      onStatus: setStatus,
    })

    return () => {
      close()
      revoke()
      setSrc(null)
      setHealth(null)
    }
  }, [cameraId])

  return { src, status, health }
}
