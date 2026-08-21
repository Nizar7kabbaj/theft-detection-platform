export const ZONE_IDS = [
  "zone-entrance",
  "zone-aisles",
  "zone-checkout",
  "zone-coolers",
  "zone-stockroom",
  "zone-backofhouse",
] as const

export type ZoneId = (typeof ZONE_IDS)[number]

export const ZONE_LABEL: Record<ZoneId, string> = {
  "zone-entrance": "entrance",
  "zone-aisles": "aisles",
  "zone-checkout": "checkout",
  "zone-coolers": "coolers",
  "zone-stockroom": "stockroom",
  "zone-backofhouse": "back of house",
}

export const ZONE_UNCOVERED_REASON: Record<ZoneId, string> = {
  "zone-entrance": "",
  "zone-aisles": "",
  "zone-checkout": "",
  "zone-coolers": "no camera covers the cooler run",
  "zone-stockroom": "",
  "zone-backofhouse": "no camera covers the back of house",
}

export const PLAN_WIDTH = 1200
export const PLAN_HEIGHT = 760
