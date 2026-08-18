"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { AlertDetail } from "@/features/alerts/schemas/alert"

const MIN_KEYPOINT_CONFIDENCE = 0.5

const BONES: readonly (readonly [number, number])[] = [
  [0, 1],
  [0, 2],
  [1, 3],
  [2, 4],
  [5, 6],
  [5, 7],
  [7, 9],
  [6, 8],
  [8, 10],
  [5, 11],
  [6, 12],
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
]

type Size = { width: number; height: number }

export function PoseOverlay({ alert }: { alert: AlertDetail }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const [size, setSize] = useState<Size | null>(null)
  const [failed, setFailed] = useState(false)

  const measure = useCallback(() => {
    const image = imageRef.current
    if (image === null) {
      return
    }
    const rect = image.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) {
      return
    }
    setSize({ width: rect.width, height: rect.height })
  }, [])

  useEffect(() => {
    const image = imageRef.current
    if (image === null) {
      return
    }
    const observer = new ResizeObserver(measure)
    observer.observe(image)
    return () => observer.disconnect()
  }, [measure])

  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas === null || size === null) {
      return
    }
    const frameWidth = alert.frame_width
    const frameHeight = alert.frame_height
    if (
      frameWidth === null ||
      frameWidth === undefined ||
      frameHeight === null ||
      frameHeight === undefined ||
      frameWidth === 0 ||
      frameHeight === 0
    ) {
      return
    }

    const ratio = window.devicePixelRatio || 1
    canvas.width = Math.round(size.width * ratio)
    canvas.height = Math.round(size.height * ratio)

    const context = canvas.getContext("2d")
    if (context === null) {
      return
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, size.width, size.height)

    const scaleX = size.width / frameWidth
    const scaleY = size.height / frameHeight
    const px = (value: number) => value * scaleX
    const py = (value: number) => value * scaleY

    const person = alert.person
    const keypoints = person?.keypoints ?? []
    const visible = keypoints.map((point) => point.confidence >= MIN_KEYPOINT_CONFIDENCE)

    if (person?.bbox !== null && person?.bbox !== undefined) {
      context.strokeStyle = "#38bdf8"
      context.lineWidth = 2
      context.setLineDash([])
      context.strokeRect(
        px(person.bbox.x1),
        py(person.bbox.y1),
        px(person.bbox.x2 - person.bbox.x1),
        py(person.bbox.y2 - person.bbox.y1),
      )
    }

    context.strokeStyle = "#38bdf8"
    context.lineWidth = 2
    context.setLineDash([])
    for (const [from, to] of BONES) {
      if (visible[from] !== true || visible[to] !== true) {
        continue
      }
      const start = keypoints[from]
      const end = keypoints[to]
      if (start === undefined || end === undefined) {
        continue
      }
      context.beginPath()
      context.moveTo(px(start.x), py(start.y))
      context.lineTo(px(end.x), py(end.y))
      context.stroke()
    }

    context.fillStyle = "#38bdf8"
    keypoints.forEach((point, index) => {
      if (visible[index] !== true) {
        return
      }
      context.beginPath()
      context.arc(px(point.x), py(point.y), 3, 0, Math.PI * 2)
      context.fill()
    })

    const concealment = alert.concealment
    const objectBbox = alert.object?.bbox

    if (objectBbox !== null && objectBbox !== undefined) {
      context.strokeStyle = "#f59e0b"
      context.lineWidth = 2
      context.setLineDash([6, 4])
      context.strokeRect(
        px(objectBbox.x1),
        py(objectBbox.y1),
        px(objectBbox.x2 - objectBbox.x1),
        py(objectBbox.y2 - objectBbox.y1),
      )
      context.setLineDash([])
    }

    if (concealment !== null && concealment !== undefined) {
      const wristX = px(concealment.wrist_x)
      const wristY = py(concealment.wrist_y)
      context.strokeStyle = "#f59e0b"
      context.lineWidth = 2
      context.setLineDash([])
      context.beginPath()
      context.arc(wristX, wristY, 7, 0, Math.PI * 2)
      context.stroke()
      context.beginPath()
      context.moveTo(wristX - 10, wristY)
      context.lineTo(wristX + 10, wristY)
      context.moveTo(wristX, wristY - 10)
      context.lineTo(wristX, wristY + 10)
      context.stroke()
    }
  }, [alert, size])

  const drawnCount =
    alert.person?.keypoints?.filter((point) => point.confidence >= MIN_KEYPOINT_CONFIDENCE)
      .length ?? 0

  return (
    <div className="flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-lg border border-border bg-muted/30">
        {failed ? (
          <div className="flex min-h-64 items-center justify-center px-6 py-12 text-center">
            <p className="text-muted-foreground text-sm">
              the stored frame could not be loaded. reload the page to try again
            </p>
          </div>
        ) : (
          <>
            {/* biome-ignore lint/performance/noImgElement: next/image proxies the request through the optimiser, which drops the session cookie, so the authenticated snapshot route answers 401 */}
            <img
              alt={`frame ${alert.frame_index} from camera ${alert.camera_id}`}
              className="block w-full"
              onError={() => setFailed(true)}
              onLoad={measure}
              ref={imageRef}
              src={alert.snapshot_url ?? ""}
            />
            {/* biome-ignore lint/a11y/noAriaHiddenOnFocusable: the canvas carries no tabindex and is not focusable. without aria-hidden a screen reader announces an empty canvas next to the frame it decorates */}
            <canvas
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 h-full w-full"
              ref={canvasRef}
            />
          </>
        )}
      </div>
      <p className="text-muted-foreground text-xs">
        solid blue is the person at frame {alert.frame_index}, {drawnCount} of{" "}
        {alert.person?.keypoints?.length ?? 0} joints above confidence {MIN_KEYPOINT_CONFIDENCE}.
        dashed amber is the object and the wrist at frame{" "}
        {alert.concealment?.last_seen_frame ?? "unknown"}, {alert.concealment?.missing_frames ?? 0}{" "}
        frames earlier
      </p>
    </div>
  )
}
