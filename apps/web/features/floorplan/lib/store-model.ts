import type { ZoneId } from "@/features/floorplan/lib/zones"

export const STORE_WIDTH = 60
export const STORE_DEPTH = 40
export const WALL_THICKNESS = 1
export const PERIMETER_HEIGHT = 10
export const PARTITION_HEIGHT = 5.5
export const CURB_HEIGHT = 1.2
export const ENTRANCE_FROM = 28
export const ENTRANCE_TO = 34

export const SOLID_VARIANTS = [
  "wall",
  "partition",
  "storefront",
  "cooler",
  "counter",
  "shelving",
  "produce",
  "fixture",
] as const

export type SolidVariant = (typeof SOLID_VARIANTS)[number]

export type Solid = {
  id: string
  x: number
  y: number
  w: number
  d: number
  h: number
  variant: SolidVariant
}

export type ZoneRect = {
  id: ZoneId
  x: number
  y: number
  w: number
  d: number
}

export const ZONE_RECTS: readonly ZoneRect[] = [
  { id: "zone-stockroom", x: 0, y: 0, w: 42, d: 11 },
  { id: "zone-backofhouse", x: 42, y: 0, w: 18, d: 11 },
  { id: "zone-aisles", x: 0, y: 12, w: 32, d: 22 },
  { id: "zone-checkout", x: 32, y: 12, w: 14, d: 24 },
  { id: "zone-coolers", x: 46, y: 12, w: 14, d: 28 },
  { id: "zone-entrance", x: 0, y: 34, w: 32, d: 6 },
]

export const SOLIDS: readonly Solid[] = [
  { id: "wall-back", x: 0, y: 0, w: 60, d: 1, h: PERIMETER_HEIGHT, variant: "wall" },
  { id: "wall-left-run", x: 0, y: 1, w: 1, d: 31, h: PERIMETER_HEIGHT, variant: "storefront" },
  { id: "entry-door-left", x: 0, y: 32, w: 1, d: 2, h: PERIMETER_HEIGHT, variant: "storefront" },
  { id: "entry-door-right", x: 0, y: 34, w: 1, d: 2, h: PERIMETER_HEIGHT, variant: "storefront" },
  { id: "wall-left-return", x: 0, y: 36, w: 1, d: 3, h: PERIMETER_HEIGHT, variant: "storefront" },
  { id: "wall-right", x: 59, y: 1, w: 1, d: 39, h: CURB_HEIGHT, variant: "wall" },
  { id: "wall-front-left", x: 1, y: 39, w: 27, d: 1, h: CURB_HEIGHT, variant: "wall" },
  { id: "wall-front-right", x: 34, y: 39, w: 25, d: 1, h: CURB_HEIGHT, variant: "wall" },
  { id: "office-desk", x: 2, y: 3, w: 5, d: 3, h: 2.5, variant: "counter" },
  { id: "crate-one", x: 12, y: 3, w: 4, d: 4, h: 4, variant: "fixture" },
  { id: "crate-two", x: 18, y: 3, w: 4, d: 4, h: 3, variant: "fixture" },
  { id: "crate-three", x: 24, y: 3, w: 5, d: 4, h: 4, variant: "fixture" },
  { id: "restroom", x: 44, y: 2, w: 5, d: 5, h: 3, variant: "fixture" },
  { id: "break-room", x: 51, y: 2, w: 7, d: 6, h: 3, variant: "fixture" },
  { id: "cooler-eight-door", x: 15, y: 12, w: 25, d: 2, h: 7, variant: "cooler" },
  { id: "cooler-beer", x: 1, y: 12, w: 3, d: 5, h: 7, variant: "cooler" },
  { id: "cooler-frozen", x: 1, y: 18, w: 3, d: 4, h: 7, variant: "cooler" },
  { id: "cooler-ice", x: 1, y: 23, w: 3, d: 4, h: 6, variant: "cooler" },
  { id: "gondola-one", x: 10, y: 16, w: 19, d: 2.5, h: 5, variant: "shelving" },
  { id: "gondola-two", x: 10, y: 21, w: 19, d: 2.5, h: 5, variant: "shelving" },
  { id: "gondola-three", x: 10, y: 26, w: 19, d: 2.5, h: 5, variant: "shelving" },
  { id: "shelf-household", x: 1, y: 28, w: 3, d: 8, h: 5, variant: "shelving" },
  { id: "gondola-four", x: 10, y: 31, w: 19, d: 2.5, h: 5, variant: "shelving" },
  { id: "tobacco-wall", x: 41, y: 16, w: 3, d: 18, h: 6, variant: "shelving" },
  { id: "roller-grill", x: 34, y: 15, w: 4, d: 6, h: 5, variant: "counter" },
  { id: "register-one", x: 34, y: 21, w: 3, d: 6, h: 3.5, variant: "counter" },
  { id: "register-two", x: 34, y: 28, w: 3, d: 6, h: 3.5, variant: "counter" },
  { id: "magazines", x: 33, y: 34, w: 8, d: 1.5, h: 3, variant: "fixture" },
  { id: "coffee-bar", x: 47, y: 25, w: 5, d: 9, h: 4, variant: "counter" },
  { id: "reach-in-one", x: 56, y: 12, w: 3, d: 6, h: 7, variant: "cooler" },
  { id: "reach-in-two", x: 56, y: 19, w: 3, d: 6, h: 7, variant: "cooler" },
  { id: "reach-in-three", x: 56, y: 26, w: 3, d: 6, h: 7, variant: "cooler" },
  { id: "reach-in-four", x: 56, y: 33, w: 3, d: 6, h: 7, variant: "cooler" },
  { id: "atm", x: 1, y: 37, w: 2, d: 2, h: 4, variant: "fixture" },
  { id: "lotto", x: 4, y: 36, w: 3, d: 1.5, h: 3, variant: "fixture" },
  { id: "seasonal", x: 8, y: 37, w: 9, d: 2, h: 3, variant: "produce" },
  { id: "news", x: 18, y: 37, w: 7, d: 2, h: 3, variant: "produce" },
]
