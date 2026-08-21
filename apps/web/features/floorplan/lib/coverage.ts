import { ZONE_IDS, type ZoneId } from "@/features/floorplan/lib/zones"

export type CameraPlacement = {
  cameraId: string
  x: number
  y: number
  height: number
  yaw: number
  fov: number
  range: number
  zone: ZoneId
}

export const PLACEMENTS: readonly CameraPlacement[] = [
  {
    cameraId: "cam-a",
    x: 16,
    y: 38,
    height: 7.5,
    yaw: 180,
    fov: 76,
    range: 26,
    zone: "zone-entrance",
  },
  {
    cameraId: "cam-b",
    x: 58,
    y: 25,
    height: 9,
    yaw: 270,
    fov: 58,
    range: 23,
    zone: "zone-aisles",
  },
  {
    cameraId: "cam-c",
    x: 25,
    y: 2,
    height: 7.5,
    yaw: 0,
    fov: 72,
    range: 19,
    zone: "zone-stockroom",
  },
]

export function placementFor(cameraId: string): CameraPlacement | null {
  return PLACEMENTS.find((placement) => placement.cameraId === cameraId) ?? null
}

export function placementForZone(zone: ZoneId): CameraPlacement | null {
  return PLACEMENTS.find((placement) => placement.zone === zone) ?? null
}

export function coveredZones(): ReadonlySet<ZoneId> {
  return new Set(PLACEMENTS.map((placement) => placement.zone))
}

export function uncoveredZones(): readonly ZoneId[] {
  const covered = coveredZones()
  return ZONE_IDS.filter((zone) => !covered.has(zone))
}
