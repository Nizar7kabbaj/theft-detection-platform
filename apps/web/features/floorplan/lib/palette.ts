"use client"
import { useEffect, useState } from "react"
export type Rgb = readonly [number, number, number]
export type Palette = {
  floor: Rgb
  floorLine: Rgb
  apron: Rgb
  wall: Rgb
  wallCap: Rgb
  partition: Rgb
  partitionCap: Rgb
  storefront: Rgb
  storefrontFrame: Rgb
  frame: Rgb
  deck: Rgb
  goods: Rgb
  produce: Rgb
  produceRim: Rgb
  counterBody: Rgb
  counterTop: Rgb
  coolerBody: Rgb
  glass: Rgb
  coolerFrame: Rgb
  sign: Rgb
  signPost: Rgb
  crate: Rgb
  crateLid: Rgb
  edge: Rgb
  label: Rgb
  zone: Rgb
  zoneActive: Rgb
  online: Rgb
  degraded: Rgb
  offline: Rgb
  unknown: Rgb
}
const FALLBACK: Rgb = [0.5, 0.5, 0.5]
const SENTINEL = "#010203"
function sample(context: CanvasRenderingContext2D, declared: string): Rgb {
  const value = declared.trim()
  if (value === "") {
    return FALLBACK
  }
  context.fillStyle = SENTINEL
  context.fillStyle = value
  if (context.fillStyle === SENTINEL && value.toLowerCase() !== SENTINEL) {
    return FALLBACK
  }
  context.clearRect(0, 0, 1, 1)
  context.fillRect(0, 0, 1, 1)
  const pixel = context.getImageData(0, 0, 1, 1).data
  const red = pixel[0]
  const green = pixel[1]
  const blue = pixel[2]
  if (red === undefined || green === undefined || blue === undefined) {
    return FALLBACK
  }
  return [red / 255, green / 255, blue / 255]
}
export function cssRgb(rgb: Rgb): string {
  const red = Math.round(rgb[0] * 255)
  const green = Math.round(rgb[1] * 255)
  const blue = Math.round(rgb[2] * 255)
  return `rgb(${red}, ${green}, ${blue})`
}
export function readPalette(): Palette {
  const styles = window.getComputedStyle(document.documentElement)
  const canvas = document.createElement("canvas")
  canvas.width = 1
  canvas.height = 1
  const context = canvas.getContext("2d", { willReadFrequently: true })
  const read = (name: string): Rgb =>
    context === null ? FALLBACK : sample(context, styles.getPropertyValue(name))
  return {
    floor: read("--plan-floor"),
    floorLine: read("--plan-floor-line"),
    apron: read("--plan-apron"),
    wall: read("--plan-wall"),
    wallCap: read("--plan-wall-cap"),
    partition: read("--plan-partition"),
    partitionCap: read("--plan-partition-cap"),
    storefront: read("--plan-storefront"),
    storefrontFrame: read("--plan-storefront-frame"),
    frame: read("--plan-frame"),
    deck: read("--plan-deck"),
    goods: read("--plan-goods"),
    produce: read("--plan-produce"),
    produceRim: read("--plan-produce-rim"),
    counterBody: read("--plan-counter-body"),
    counterTop: read("--plan-counter-top"),
    coolerBody: read("--plan-cooler-body"),
    glass: read("--plan-glass"),
    coolerFrame: read("--plan-cooler-frame"),
    sign: read("--plan-sign"),
    signPost: read("--plan-sign-post"),
    crate: read("--plan-crate"),
    crateLid: read("--plan-crate-lid"),
    edge: read("--plan-edge"),
    label: read("--plan-label"),
    zone: read("--plan-zone"),
    zoneActive: read("--plan-zone-active"),
    online: read("--success"),
    degraded: read("--warning"),
    offline: read("--destructive"),
    unknown: read("--muted-foreground"),
  }
}
export function usePlanPalette(): Palette | null {
  const [palette, setPalette] = useState<Palette | null>(null)
  useEffect(() => {
    const refresh = (): void => {
      setPalette(readPalette())
    }
    refresh()
    const observer = new MutationObserver(refresh)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    return () => {
      observer.disconnect()
    }
  }, [])
  return palette
}
