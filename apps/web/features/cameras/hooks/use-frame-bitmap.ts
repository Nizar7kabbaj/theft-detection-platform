"use client"

import { type RefObject, useEffect, useRef, useState } from "react"
import type { PoseFigure } from "@/features/cameras/components/frame-canvas"
import {
  type DetectionFrame,
  type FrameHealth,
  type FrameStatus,
  openFrameSocket,
} from "@/features/cameras/lib/frame-socket"

const STATS_INTERVAL_MS = 1000
const DETECTION_STALE_MS = 2000

export type FrameStats = {
  fps: number | null
  frames: number
  lastFrameAt: string | null
  width: number | null
  height: number | null
  persons: number | null
  inferenceState: string | null
}

export type FrameBitmap = {
  bitmapRef: RefObject<ImageBitmap | null>
  status: FrameStatus
  health: FrameHealth | null
  stats: FrameStats
  pose: PoseFigure[] | null
}

const IDLE_STATS: FrameStats = {
  fps: null,
  frames: 0,
  lastFrameAt: null,
  width: null,
  height: null,
  persons: null,
  inferenceState: null,
}

function toPose(detection: DetectionFrame): PoseFigure[] {
  const width = detection.frame_width
  const height = detection.frame_height
  if (width <= 0 || height <= 0) {
    return []
  }
  return detection.persons.map((person) => ({
    keypoints: person.keypoints.map((point) => ({
      x: point.x / width,
      y: point.y / height,
      confidence: point.confidence,
    })),
  }))
}

function leadState(detection: DetectionFrame): string | null {
  const lead = detection.persons[0]
  return lead === undefined ? null : lead.inference_state
}

export function useFrameBitmap(cameraId: string): FrameBitmap {
  const bitmapRef = useRef<ImageBitmap | null>(null)
  const [status, setStatus] = useState<FrameStatus>("connecting")
  const [health, setHealth] = useState<FrameHealth | null>(null)
  const [stats, setStats] = useState<FrameStats>(IDLE_STATS)
  const [pose, setPose] = useState<PoseFigure[] | null>(null)

  useEffect(() => {
    let cancelled = false
    let decoding = false
    let windowCount = 0
    let totalCount = 0
    let arrivedAt: number | null = null
    let frameWidth: number | null = null
    let frameHeight: number | null = null
    let personCount: number | null = null
    let inferenceState: string | null = null
    let detectionAt = 0

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
            frameWidth = bitmap.width
            frameHeight = bitmap.height
          })
          .catch(() => {})
          .finally(() => {
            decoding = false
          })
      },
      onHealth: setHealth,
      onStatus: setStatus,
      onDetection: (detection) => {
        detectionAt = Date.now()
        personCount = detection.persons.length
        inferenceState = leadState(detection)
        setPose(toPose(detection))
      },
    })

    const ticker = window.setInterval(() => {
      const measured = windowCount
      windowCount = 0
      const fresh = Date.now() - detectionAt < DETECTION_STALE_MS
      if (!fresh) {
        personCount = null
        inferenceState = null
        setPose(null)
      }
      setStats({
        fps: measured,
        frames: totalCount,
        lastFrameAt: arrivedAt === null ? null : new Date(arrivedAt).toISOString(),
        width: frameWidth,
        height: frameHeight,
        persons: personCount,
        inferenceState,
      })
    }, STATS_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearInterval(ticker)
      close()
      release()
      setHealth(null)
      setStats(IDLE_STATS)
      setPose(null)
    }
  }, [cameraId])

  return { bitmapRef, status, health, stats, pose }
}
