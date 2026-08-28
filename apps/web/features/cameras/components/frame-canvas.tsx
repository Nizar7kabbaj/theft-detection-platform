"use client"

import { Video } from "lucide-react"
import type { RefObject } from "react"
import { useCallback, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import type { FrameHealth, FrameStatus } from "@/features/cameras/lib/frame-socket"

const STATUS_NOTICE: Record<FrameStatus, string> = {
  connecting: "connecting",
  open: "",
  waiting: "reconnecting",
  stopped: "stream unavailable",
}

const HEALTH_DOT: Record<FrameHealth, string> = {
  online: "bg-success shadow-[0_0_8px_2px_rgba(73,229,157,.55)]",
  degraded: "bg-warning shadow-[0_0_8px_2px_rgba(242,181,68,.55)]",
  offline: "bg-destructive shadow-[0_0_8px_2px_rgba(255,92,99,.55)]",
  unknown: "bg-muted-foreground/50",
}

const SCANLINES =
  "repeating-linear-gradient(180deg, rgba(255,255,255,.035) 0px, rgba(255,255,255,.035) 1px, transparent 1px, transparent 4px)"

const VIGNETTE = "radial-gradient(ellipse at center, rgba(255,255,255,.05) 0%, transparent 70%)"

const LIMBS: readonly (readonly [number, number, string])[] = [
  [0, 1, "#f2b544"],
  [0, 2, "#f2b544"],
  [1, 3, "#f2b544"],
  [2, 4, "#f2b544"],
  [5, 6, "#ff5c63"],
  [5, 7, "#6b9bff"],
  [7, 9, "#6b9bff"],
  [6, 8, "#49e59d"],
  [8, 10, "#49e59d"],
  [5, 11, "#ff5c63"],
  [6, 12, "#ff5c63"],
  [11, 12, "#ff5c63"],
  [11, 13, "#6b9bff"],
  [13, 15, "#6b9bff"],
  [12, 14, "#49e59d"],
  [14, 16, "#49e59d"],
]

export type PosePoint = { x: number; y: number; confidence: number }
export type PoseFigure = { keypoints: PosePoint[] }

type Box = { x: number; y: number; width: number; height: number }

function fitBox(
  frameWidth: number,
  frameHeight: number,
  viewWidth: number,
  viewHeight: number,
): Box {
  const scale = Math.min(viewWidth / frameWidth, viewHeight / frameHeight)
  const width = frameWidth * scale
  const height = frameHeight * scale
  return {
    x: (viewWidth - width) / 2,
    y: (viewHeight - height) / 2,
    width,
    height,
  }
}

function drawPose(
  context: CanvasRenderingContext2D,
  figures: PoseFigure[],
  box: Box,
  threshold: number,
): void {
  for (const figure of figures) {
    const points = figure.keypoints
    context.lineCap = "round"
    context.lineWidth = Math.max(2, box.width / 220)
    for (const [from, to, color] of LIMBS) {
      const start = points[from]
      const end = points[to]
      if (start === undefined || end === undefined) {
        continue
      }
      const weak = start.confidence < threshold || end.confidence < threshold
      context.globalAlpha = weak ? 0.25 : 1
      context.strokeStyle = color
      context.beginPath()
      context.moveTo(box.x + start.x * box.width, box.y + start.y * box.height)
      context.lineTo(box.x + end.x * box.width, box.y + end.y * box.height)
      context.stroke()
    }
    const radius = Math.max(2.5, box.width / 260)
    for (const point of points) {
      context.globalAlpha = point.confidence < threshold ? 0.25 : 1
      context.fillStyle = "#e7e4df"
      context.beginPath()
      context.arc(box.x + point.x * box.width, box.y + point.y * box.height, radius, 0, Math.PI * 2)
      context.fill()
    }
    context.globalAlpha = 1
  }
}

export function FrameCanvas({
  bitmapRef,
  status,
  health,
  cameraName,
  pose,
  threshold,
  height,
}: {
  bitmapRef: RefObject<ImageBitmap | null>
  status: FrameStatus
  health: FrameHealth | null
  cameraName: string
  pose: PoseFigure[] | null
  threshold: number
  height?: string | undefined
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const surfaceRef = useRef<HTMLDivElement | null>(null)
  const poseRef = useRef<PoseFigure[] | null>(pose)
  const thresholdRef = useRef(threshold)

  poseRef.current = pose
  thresholdRef.current = threshold

  useEffect(() => {
    let frameHandle = 0

    const paint = (): void => {
      frameHandle = window.requestAnimationFrame(paint)
      const canvas = canvasRef.current
      if (canvas === null) {
        return
      }
      const rect = canvas.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) {
        return
      }
      const ratio = window.devicePixelRatio || 1
      const pixelWidth = Math.round(rect.width * ratio)
      const pixelHeight = Math.round(rect.height * ratio)
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth
        canvas.height = pixelHeight
      }
      const context = canvas.getContext("2d")
      if (context === null) {
        return
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      context.clearRect(0, 0, rect.width, rect.height)
      const bitmap = bitmapRef.current
      if (bitmap === null) {
        return
      }
      const box = fitBox(bitmap.width, bitmap.height, rect.width, rect.height)
      context.drawImage(bitmap, box.x, box.y, box.width, box.height)
      const figures = poseRef.current
      if (figures !== null && figures.length > 0) {
        drawPose(context, figures, box, thresholdRef.current)
      }
    }

    frameHandle = window.requestAnimationFrame(paint)
    return () => {
      window.cancelAnimationFrame(frameHandle)
    }
  }, [bitmapRef])

  const toggleFullscreen = useCallback(() => {
    const node = surfaceRef.current
    if (node === null) {
      return
    }
    if (document.fullscreenElement === node) {
      void document.exitFullscreen()
      return
    }
    void node.requestFullscreen()
  }, [])

  const notice = STATUS_NOTICE[status]
  const state = health ?? "unknown"

  return (
    <div
      className={`relative aspect-video w-full overflow-hidden rounded-lg border border-border bg-black ${height ?? "max-h-[34rem]"}`}
      ref={surfaceRef}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0"
        style={{ backgroundImage: `${VIGNETTE}, ${SCANLINES}` }}
      />
      <canvas
        aria-label={`current frame from ${cameraName}`}
        className="relative block size-full"
        ref={canvasRef}
        role="img"
      />
      {bitmapRef.current === null ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2.5">
          <Video aria-hidden="true" className="size-7 text-muted-foreground/50" />
          <span className="font-mono text-muted-foreground text-xs uppercase">
            {notice === "" ? "waiting for frames" : notice}
          </span>
        </div>
      ) : null}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-3">
        <span className="flex items-center gap-1.5 rounded-sm bg-black/60 px-2 py-1 font-mono text-[10px] text-white uppercase">
          <span
            aria-hidden="true"
            className={`size-1.5 rounded-full ${HEALTH_DOT[state]} ${state === "online" ? "animate-pulse" : ""}`}
          />
          {state}
        </span>
        <Button
          className="pointer-events-auto"
          onClick={toggleFullscreen}
          size="sm"
          type="button"
          variant="secondary"
        >
          fullscreen
        </Button>
      </div>
    </div>
  )
}
