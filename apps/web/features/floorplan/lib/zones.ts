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
