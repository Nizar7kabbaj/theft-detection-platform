import type { Color } from "three"
import { CanvasTexture, SRGBColorSpace } from "three"
import {
  buildSolid,
  disposeSolid,
  type SolidParts,
  type Tints,
} from "@/features/floorplan/lib/fixture-geometry"
import { SOLIDS, type Solid, ZONE_RECTS } from "@/features/floorplan/lib/store-model"
import { ZONE_LABEL, type ZoneId } from "@/features/floorplan/lib/zones"

export const LABEL_HEIGHT = 2.1
const LABEL_PIXELS = 72

export type BuiltSolid = {
  solid: Solid
  parts: SolidParts
}

export type LabelEntry = {
  id: ZoneId
  texture: CanvasTexture
  width: number
}

let solidKey: string | null = null
let solidCache: readonly BuiltSolid[] | null = null

let labelKey: string | null = null
let labelCache: readonly LabelEntry[] | null = null

function tintKey(tints: Tints): string {
  return `${tints.goods.getHexString()}:${tints.produce.getHexString()}`
}

export function cachedSolids(tints: Tints): readonly BuiltSolid[] {
  const key = tintKey(tints)
  if (key === solidKey && solidCache !== null) {
    return solidCache
  }
  if (solidCache !== null) {
    for (const entry of solidCache) {
      disposeSolid(entry.parts)
    }
  }
  const built = SOLIDS.map((solid) => ({ solid, parts: buildSolid(solid, tints) }))
  solidKey = key
  solidCache = built
  return built
}

function drawLabel(text: string, fill: string): { texture: CanvasTexture; aspect: number } | null {
  const canvas = document.createElement("canvas")
  const measure = canvas.getContext("2d")
  if (measure === null) {
    return null
  }
  const font = `600 ${LABEL_PIXELS}px Inter, system-ui, sans-serif`
  measure.font = font
  const width = Math.ceil(measure.measureText(text).width) + LABEL_PIXELS
  const height = Math.ceil(LABEL_PIXELS * 1.7)
  canvas.width = width
  canvas.height = height
  const paint = canvas.getContext("2d")
  if (paint === null) {
    return null
  }
  paint.font = font
  paint.fillStyle = fill
  paint.textAlign = "center"
  paint.textBaseline = "middle"
  paint.fillText(text, width / 2, height / 2)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  texture.anisotropy = 8
  return { texture, aspect: width / height }
}

export function peekLabels(fill: string): readonly LabelEntry[] | null {
  return fill === labelKey ? labelCache : null
}

export function cachedLabels(fill: string): readonly LabelEntry[] {
  const hit = peekLabels(fill)
  if (hit !== null) {
    return hit
  }
  if (labelCache !== null) {
    for (const entry of labelCache) {
      entry.texture.dispose()
    }
  }
  const built: LabelEntry[] = []
  for (const rect of ZONE_RECTS) {
    const made = drawLabel(ZONE_LABEL[rect.id], fill)
    if (made === null) {
      continue
    }
    built.push({ id: rect.id, texture: made.texture, width: LABEL_HEIGHT * made.aspect })
  }
  labelKey = fill
  labelCache = built
  return built
}

export function tintsFrom(goods: Color, produce: Color): Tints {
  return { goods, produce }
}
