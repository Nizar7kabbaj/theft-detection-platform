"use client"

import type { Camera } from "@/features/cameras/schemas/camera"

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="shrink-0 font-mono text-[9px] text-muted-foreground uppercase">{label}</span>
      <span className="min-w-0 truncate font-mono text-xs">{value}</span>
    </div>
  )
}

export function CameraDetail({ camera }: { camera: Camera }) {
  const source =
    camera.stream_url === null || camera.stream_url === undefined
      ? "no stream url"
      : camera.stream_url

  return (
    <div className="flex w-64 min-w-0 flex-col gap-2">
      <Row label="identifier" value={camera.camera_id} />
      <Row label="status" value={camera.status} />
      <Row label="source" value={source} />
      <Row label="registered" value={camera.created_at.slice(0, 10)} />
    </div>
  )
}
