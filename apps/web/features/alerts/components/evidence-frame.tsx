"use client"
import { Video } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { ClipDialog } from "@/features/alerts/components/clip-dialog"
import { useAlertDetail } from "@/features/alerts/hooks/use-alert-detail"
import { objectLabel } from "@/features/alerts/lib/format"
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
const HEAD_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.16em]"
const TOGGLE_CLASS =
  "h-7 rounded-md px-2.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors"
const TOGGLE_ON = `${TOGGLE_CLASS} bg-info/15 text-info`
const TOGGLE_OFF = `${TOGGLE_CLASS} text-muted-foreground hover:bg-muted hover:text-foreground`

type Rect = { width: number; height: number }

function readToken(element: Element, name: string, fallback: string): string {
  const value = getComputedStyle(element).getPropertyValue(name).trim()
  return value === "" ? fallback : value
}

export function EvidenceFrame({ alert }: { alert: AlertDetail }) {
  const { data } = useAlertDetail(alert._id, alert)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const shellRef = useRef<HTMLDivElement | null>(null)
  const [box, setBox] = useState<Rect | null>(null)
  const [failed, setFailed] = useState(false)
  const [skeleton, setSkeleton] = useState(true)
  const [clipOpen, setClipOpen] = useState(false)
  const [watched, setWatched] = useState(true)

  const measure = useCallback(() => {
    const shell = shellRef.current
    if (shell === null) {
      return
    }
    const rect = shell.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) {
      return
    }
    setBox({ width: rect.width, height: rect.height })
  }, [])

  useEffect(() => {
    const shell = shellRef.current
    if (shell === null) {
      return
    }
    const observer = new ResizeObserver(measure)
    observer.observe(shell)
    return () => observer.disconnect()
  }, [measure])

  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas === null || box === null) {
      return
    }
    const frameWidth = data.frame_width
    const frameHeight = data.frame_height
    const ratio = window.devicePixelRatio || 1
    canvas.width = Math.round(box.width * ratio)
    canvas.height = Math.round(box.height * ratio)
    const context = canvas.getContext("2d")
    if (context === null) {
      return
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, box.width, box.height)
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
    const personColour = readToken(canvas, "--info", "#6b9bff")
    const objectColour = readToken(canvas, "--warning", "#f2b544")
    const wristColour = readToken(canvas, "--destructive", "#ff5c63")
    const scale = Math.min(box.width / frameWidth, box.height / frameHeight)
    const offsetX = (box.width - frameWidth * scale) / 2
    const offsetY = (box.height - frameHeight * scale) / 2
    const px = (value: number) => offsetX + value * scale
    const py = (value: number) => offsetY + value * scale
    const person = data.person
    const keypoints = person?.keypoints ?? []
    const visible = keypoints.map((point) => point.confidence >= MIN_KEYPOINT_CONFIDENCE)
    const wristIndex = data.concealment?.wrist_index ?? -1

    context.lineWidth = 2
    context.setLineDash([])
    if (person?.bbox !== null && person?.bbox !== undefined) {
      context.strokeStyle = personColour
      context.strokeRect(
        px(person.bbox.x1),
        py(person.bbox.y1),
        (person.bbox.x2 - person.bbox.x1) * scale,
        (person.bbox.y2 - person.bbox.y1) * scale,
      )
    }
    const objectBbox = data.object?.bbox
    if (objectBbox !== null && objectBbox !== undefined) {
      context.strokeStyle = objectColour
      context.setLineDash([6, 4])
      context.strokeRect(
        px(objectBbox.x1),
        py(objectBbox.y1),
        (objectBbox.x2 - objectBbox.x1) * scale,
        (objectBbox.y2 - objectBbox.y1) * scale,
      )
      context.setLineDash([])
    }
    if (!skeleton) {
      return
    }
    context.strokeStyle = personColour
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
    keypoints.forEach((point, index) => {
      if (visible[index] !== true) {
        return
      }
      context.fillStyle = index === wristIndex ? wristColour : "#ffffff"
      context.beginPath()
      context.arc(px(point.x), py(point.y), index === wristIndex ? 4.5 : 2.5, 0, Math.PI * 2)
      context.fill()
    })
  }, [box, data, skeleton])

  const source = data.snapshot_url
  const clip = data.clip_url
  const clipKey = `alert-clip-watched:${data._id}`

  const [prefetch, setPrefetch] = useState(false)

  useEffect(() => {
    setWatched(window.localStorage.getItem(clipKey) === "1")
  }, [clipKey])
  const total = data.person?.keypoints?.length ?? 0
  const drawn =
    data.person?.keypoints?.filter((point) => point.confidence >= MIN_KEYPOINT_CONFIDENCE).length ??
    0
  const wristIndex = data.concealment?.wrist_index

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className={HEAD_CLASS}>
          {data.camera_id} · {data.frame_width ?? "?"}×{data.frame_height ?? "?"} · stored jpeg
        </p>
        <fieldset className="flex items-center gap-1">
          <legend className="sr-only">frame annotations</legend>
          <button
            className={skeleton ? TOGGLE_OFF : TOGGLE_ON}
            onClick={() => setSkeleton(false)}
            type="button"
          >
            boxes
          </button>
          <button
            className={skeleton ? TOGGLE_ON : TOGGLE_OFF}
            onClick={() => setSkeleton(true)}
            type="button"
          >
            boxes + skeleton
          </button>
        </fieldset>
      </div>
      <div
        className="relative aspect-video overflow-hidden rounded-md bg-black outline outline-border"
        ref={shellRef}
      >
        {source === null || source === undefined || failed ? (
          <p className="absolute inset-0 flex items-center justify-center px-6 text-center text-muted-foreground text-sm">
            {source === null || source === undefined
              ? "no snapshot was stored for this alert"
              : "the stored frame could not be loaded. reload the page to try again"}
          </p>
        ) : (
          <img
            alt={`frame ${data.frame_index} from camera ${data.camera_id}`}
            className="absolute inset-0 size-full object-contain"
            onError={() => setFailed(true)}
            onLoad={measure}
            src={source}
          />
        )}
        <canvas
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 size-full"
          ref={canvasRef}
        />
        {clip === null || clip === undefined ? null : (
          <div className="group absolute right-4 bottom-4">
            {watched ? null : <span aria-hidden="true" className="clip-ring" />}
            <button
              aria-label="watch the recorded clip"
              className="relative inline-flex h-14 items-center gap-2 rounded-full bg-gradient-to-r from-[#81e6d9] to-[#4fd1c5] px-4 font-medium text-[#313133] text-base shadow-[0_0_24px_rgba(79,209,197,0.64)] transition-transform duration-300 hover:-translate-y-1.5 hover:scale-105 [&_svg]:size-6"
              onFocus={() => setPrefetch(true)}
              onMouseEnter={() => setPrefetch(true)}
              onClick={() => {
                setClipOpen(true)
                setWatched(true)
                window.localStorage.setItem(clipKey, "1")
              }}
              type="button"
            >
              <Video aria-hidden="true" className="shrink-0" />
              <span className="flex max-w-0 items-center overflow-hidden whitespace-nowrap opacity-0 transition-[max-width,opacity] duration-200 ease-out group-hover:max-w-40 group-hover:opacity-100 group-focus-visible:max-w-40 group-focus-visible:opacity-100">
                watch clip
              </span>
            </button>
            {prefetch ? (
              <video className="hidden" muted preload="auto" src={clip}>
                <track kind="captions" />
              </video>
            ) : null}
          </div>
        )}
      </div>
      <p className="text-muted-foreground text-xs text-pretty">
        boxes identify person {data.person?.track_id ?? "unknown"} and {objectLabel(data)}.{" "}
        {skeleton
          ? `skeleton shows ${drawn} of ${total} joints at confidence ${MIN_KEYPOINT_CONFIDENCE} or higher`
          : "skeleton hidden"}
        {wristIndex === null || wristIndex === undefined
          ? ""
          : `, the red joint is wrist index ${wristIndex}`}
      </p>
      {clip === null || clip === undefined ? null : (
        <ClipDialog
          cameraId={data.camera_id}
          onOpenChange={setClipOpen}
          open={clipOpen}
          source={clip}
        />
      )}
    </div>
  )
}
