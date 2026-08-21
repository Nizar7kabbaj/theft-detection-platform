import { BoxGeometry, BufferAttribute, type BufferGeometry, type Color, EdgesGeometry } from "three"
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js"
import { type Solid, STORE_DEPTH, STORE_WIDTH } from "@/features/floorplan/lib/store-model"

export type PartKind =
  | "wall"
  | "wallCap"
  | "partition"
  | "partitionCap"
  | "storefront"
  | "storefrontFrame"
  | "frame"
  | "deck"
  | "goods"
  | "produce"
  | "produceRim"
  | "counterBody"
  | "counterTop"
  | "coolerBody"
  | "glass"
  | "coolerFrame"
  | "sign"
  | "signPost"
  | "crate"
  | "crateLid"

export type Tints = {
  goods: Color
  produce: Color
}

export type SolidPart = {
  kind: PartKind
  geometry: BufferGeometry
}

export type SolidParts = {
  parts: readonly SolidPart[]
  edges: BufferGeometry | null
}

type Push = (kind: PartKind, geometry: BufferGeometry) => void

const MIN_SIZE = 0.02
const PLINTH = 0.35
const UPRIGHT = 0.14
const DECK = 0.12
const BACK = 0.16
const ROOM_AREA = 24

function box(
  width: number,
  height: number,
  depth: number,
  cx: number,
  cy: number,
  cz: number,
): BufferGeometry {
  const geometry = new BoxGeometry(
    Math.max(MIN_SIZE, width),
    Math.max(MIN_SIZE, height),
    Math.max(MIN_SIZE, depth),
  )
  geometry.translate(cx, cy, cz)
  return geometry
}

function tinted(geometry: BufferGeometry, color: Color): BufferGeometry {
  const position = geometry.getAttribute("position")
  const total = position.count
  const values = new Float32Array(total * 3)
  for (let index = 0; index < total; index += 1) {
    values[index * 3] = color.r
    values[index * 3 + 1] = color.g
    values[index * 3 + 2] = color.b
  }
  geometry.setAttribute("color", new BufferAttribute(values, 3))
  return geometry
}

function hashUnit(id: string): number {
  let value = 2166136261
  for (let index = 0; index < id.length; index += 1) {
    value ^= id.charCodeAt(index)
    value = Math.imul(value, 16777619)
  }
  return ((value >>> 0) % 997) / 997
}

function signBand(length: number, height: number, bandHeight: number, push: Push): void {
  const gap = 0.35
  push("sign", box(length - 0.2, bandHeight, 0.18, 0, height + gap + bandHeight / 2, 0))
  const inset = Math.min(0.5, length / 4)
  push("signPost", box(0.09, gap, 0.09, length / 2 - inset, height + gap / 2, 0))
  push("signPost", box(0.09, gap, 0.09, inset - length / 2, height + gap / 2, 0))
}

function shelving(
  length: number,
  thickness: number,
  height: number,
  tints: Tints,
  seed: number,
  push: Push,
): void {
  push("frame", box(length, PLINTH, thickness, 0, PLINTH / 2, 0))
  push("frame", box(UPRIGHT, height, thickness, length / 2 - UPRIGHT / 2, height / 2, 0))
  push("frame", box(UPRIGHT, height, thickness, UPRIGHT / 2 - length / 2, height / 2, 0))
  push(
    "frame",
    box(length - UPRIGHT * 2, height - PLINTH, BACK, 0, PLINTH + (height - PLINTH) / 2, 0),
  )
  const levels = Math.min(5, Math.max(2, Math.round((height - PLINTH) / 1.15)))
  const step = (height - PLINTH) / levels
  const span = length - UPRIGHT * 2 - 0.08
  const side = Math.max(0.3, (thickness - BACK) / 2)
  const columns = Math.max(2, Math.round(span / 2.4))
  const columnWidth = span / columns
  for (let level = 0; level < levels; level += 1) {
    const base = PLINTH + level * step
    const depth = side * (1 - level * 0.07)
    const offset = BACK / 2 + depth / 2
    const stack = step * 0.58
    for (const face of [1, -1]) {
      push("deck", box(span, DECK, depth, 0, base + DECK / 2, face * offset))
      for (let column = 0; column < columns; column += 1) {
        const cx = columnWidth / 2 + column * columnWidth - span / 2
        const spin = (seed + level * 0.17 + column * 0.29 + (face > 0 ? 0 : 0.11)) % 1
        const tint = tints.goods.clone().offsetHSL(spin * 0.62 - 0.31, 0, spin * 0.1 - 0.05)
        push(
          "goods",
          tinted(
            box(
              columnWidth - 0.14,
              stack,
              depth * 0.74,
              cx,
              base + DECK + stack / 2,
              face * offset,
            ),
            tint,
          ),
        )
      }
    }
  }
  signBand(length, height, 0.75, push)
}

function cooler(length: number, thickness: number, height: number, push: Push): void {
  push("coolerBody", box(length, height, thickness, 0, height / 2, 0))
  const doors = Math.max(1, Math.round(length / 3.1))
  const mullion = 0.2
  const width = (length - mullion * (doors + 1)) / doors
  if (width > 0.3) {
    const glassHeight = height - 1.2
    for (let door = 0; door < doors; door += 1) {
      const cx = mullion + width / 2 + door * (width + mullion) - length / 2
      push(
        "coolerFrame",
        box(
          width + mullion,
          glassHeight + 0.18,
          0.1,
          cx,
          0.7 + glassHeight / 2,
          thickness / 2 + 0.03,
        ),
      )
      push("glass", box(width, glassHeight, 0.12, cx, 0.7 + glassHeight / 2, thickness / 2 + 0.09))
    }
  }
  signBand(length, height, 0.7, push)
}

function counter(length: number, thickness: number, height: number, push: Push): void {
  push("counterTop", box(length - 0.6, 0.26, thickness - 0.6, 0, 0.13, 0))
  push("counterBody", box(length, height - 0.5, thickness, 0, 0.26 + (height - 0.5) / 2, 0))
  push("counterTop", box(length + 0.2, 0.2, thickness + 0.2, 0, height - 0.1, 0))
}

function produceBin(
  length: number,
  thickness: number,
  height: number,
  tints: Tints,
  seed: number,
  push: Push,
): void {
  const body = height * 0.62
  push("produce", box(length, body, thickness, 0, body / 2, 0))
  push("produceRim", box(length + 0.16, 0.18, thickness + 0.16, 0, body + 0.09, 0))
  const columns = Math.max(2, Math.round(length / 2.6))
  const columnWidth = (length - 0.3) / columns
  const mound = height - body - 0.18
  for (let column = 0; column < columns; column += 1) {
    const cx = columnWidth / 2 + column * columnWidth - (length - 0.3) / 2
    const spin = (seed + column * 0.37) % 1
    const tint = tints.produce.clone().offsetHSL(spin * 0.5 - 0.16, 0, spin * 0.09 - 0.04)
    push(
      "goods",
      tinted(box(columnWidth - 0.12, mound, thickness - 0.3, cx, body + 0.18 + mound / 2, 0), tint),
    )
  }
}

function storefront(length: number, thickness: number, height: number, push: Push): void {
  push("storefrontFrame", box(length, 0.6, thickness, 0, 0.3, 0))
  push("storefrontFrame", box(length, 0.5, thickness, 0, height - 0.25, 0))
  const panes = Math.max(1, Math.round(length / 4.2))
  const mullion = 0.24
  const width = (length - mullion * (panes + 1)) / panes
  const glassHeight = height - 1.1
  push("storefrontFrame", box(length, glassHeight, thickness * 0.5, 0, 0.6 + glassHeight / 2, 0))
  if (width > 0.3) {
    for (let pane = 0; pane < panes; pane += 1) {
      const cx = mullion + width / 2 + pane * (width + mullion) - length / 2
      push("storefront", box(width, glassHeight, thickness * 0.8, cx, 0.6 + glassHeight / 2, 0))
    }
  }
}

function slab(
  length: number,
  thickness: number,
  height: number,
  body: PartKind,
  cap: PartKind,
  overhang: number,
  push: Push,
): void {
  push(body, box(length, height - 0.16, thickness, 0, (height - 0.16) / 2, 0))
  push(cap, box(length + overhang, 0.16, thickness + overhang, 0, height - 0.08, 0))
}

function orient(geometry: BufferGeometry, alongX: boolean, positive: boolean): BufferGeometry {
  if (alongX) {
    if (!positive) {
      geometry.rotateY(Math.PI)
    }
    return geometry
  }
  geometry.rotateY(positive ? Math.PI / 2 : -Math.PI / 2)
  return geometry
}

export function buildSolid(solid: Solid, tints: Tints): SolidParts {
  const groups = new Map<PartKind, BufferGeometry[]>()
  const push: Push = (kind, geometry) => {
    const list = groups.get(kind)
    if (list === undefined) {
      groups.set(kind, [geometry])
    } else {
      list.push(geometry)
    }
  }
  const alongX = solid.w >= solid.d
  const length = alongX ? solid.w : solid.d
  const thickness = alongX ? solid.d : solid.w
  const positive = alongX
    ? solid.y + solid.d / 2 < STORE_DEPTH / 2
    : solid.x + solid.w / 2 < STORE_WIDTH / 2
  const seed = hashUnit(solid.id)
  if (solid.variant === "wall") {
    slab(length, thickness, solid.h, "wall", "wallCap", 0.06, push)
  } else if (solid.variant === "partition") {
    slab(length, thickness, solid.h, "partition", "partitionCap", 0.06, push)
  } else if (solid.variant === "storefront") {
    storefront(length, thickness, solid.h, push)
  } else if (solid.variant === "shelving") {
    shelving(length, thickness, solid.h, tints, seed, push)
  } else if (solid.variant === "cooler") {
    cooler(length, thickness, solid.h, push)
  } else if (solid.variant === "counter") {
    counter(length, thickness, solid.h, push)
  } else if (solid.variant === "produce") {
    produceBin(length, thickness, solid.h, tints, seed, push)
  } else if (solid.w * solid.d >= ROOM_AREA) {
    slab(length, thickness, solid.h, "partition", "partitionCap", 0.06, push)
  } else {
    slab(length, thickness, solid.h, "crate", "crateLid", 0.12, push)
  }
  const parts: SolidPart[] = []
  const outlines: BufferGeometry[] = []
  for (const [kind, list] of groups) {
    const merged = mergeGeometries(list)
    for (const piece of list) {
      piece.dispose()
    }
    if (merged === null) {
      continue
    }
    const shaped = orient(merged, alongX, positive)
    parts.push({ kind, geometry: shaped })
    outlines.push(new EdgesGeometry(shaped, 25))
  }
  const edges = outlines.length === 0 ? null : mergeGeometries(outlines)
  for (const outline of outlines) {
    outline.dispose()
  }
  return { parts, edges }
}

export function disposeSolid(built: SolidParts): void {
  for (const part of built.parts) {
    part.geometry.dispose()
  }
  if (built.edges !== null) {
    built.edges.dispose()
  }
}
