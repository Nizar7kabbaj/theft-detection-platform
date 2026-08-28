"use client"

import { type RefObject, useEffect, useRef, useState } from "react"
import {
  type FrameHealth,
  type FrameStatus,
  openFrameSocket,
} from "@/features/cameras/lib/frame-socket"

const STATS_INTERVAL_MS = 1000

export type FrameStats = {
  fps: number | null
  frames: number
  lastFrameAt: string | null
}

export type FrameBitmap = {
  bitmapRef: RefObject<ImageBitmap | null>
  status: FrameStatus
  health: FrameHealth | null
  stats: FrameStats
}

const IDLE_STATS: FrameStats = { fps: null, frames: 0, lastFrameAt: null }

export function useFrameBitmap(cameraId: string): FrameBitmap {
  const bitmapRef = useRef<ImageBitmap | null>(null)
  const [status, setStatus] = useState<FrameStatus>("connecting")
  const [health, setHealth] = useState<FrameHealth | null>(null)
  const [stats, setStats] = useState<FrameStats>(IDLE_STATS)

  useEffect(() => {
    let cancelled = false
    let decoding = false
    let windowCount = 0
    let totalCount = 0
    let arrivedAt: number | null = null

    const release = (): void => {
      const current = bitmapRef.current
      bitmapRef.current = null
      if (current !== null) {
        current.close()
      }
    }

    const adopt = (bitmap: ImageBitmap): void => {
      const previous = bitmapRef.current
      bitmapRef.current = bitmap
      if (previous !== null) {
        previous.close()
      }
    }

    const close = openFrameSocket(cameraId, {
      onFrame: (blob) => {
        if (decoding) {
          return
        }
        decoding = true
        void createImageBitmap(blob)
          .then((bitmap) => {
            if (cancelled) {
              bitmap.close()
              return
            }
            adopt(bitmap)
            windowCount += 1
            totalCount += 1
            arrivedAt = Date.now()
          })
          .catch(() => {})
          .finally(() => {
            decoding = false
          })
      },
      onHealth: setHealth,
      onStatus: setStatus,
    })

    const ticker = window.setInterval(() => {
      const measured = windowCount
      windowCount = 0
      setStats({
        fps: measured,
        frames: totalCount,
        lastFrameAt: arrivedAt === null ? null : new Date(arrivedAt).toISOString(),
      })
    }, STATS_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearInterval(ticker)
      close()
      release()
      setHealth(null)
      setStats(IDLE_STATS)
    }
  }, [cameraId])

  return { bitmapRef, status, health, stats }
}
