"use client"
import { ContactShadows, OrbitControls } from "@react-three/drei"
import { Canvas, type ThreeEvent, useThree } from "@react-three/fiber"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  BufferAttribute,
  BufferGeometry,
  Color,
  LineBasicMaterial,
  MeshStandardMaterial,
  type Object3D,
  SRGBColorSpace,
} from "three"
import type { HealthState } from "@/features/cameras/schemas/camera"
import { type CameraPlacement, PLACEMENTS } from "@/features/floorplan/lib/coverage"
import type { PartKind } from "@/features/floorplan/lib/fixture-geometry"
import { cssRgb, type Palette, type Rgb } from "@/features/floorplan/lib/palette"
import {
  cachedLabels,
  cachedSolids,
  dropSceneCache,
  LABEL_HEIGHT,
  type LabelEntry,
  peekLabels,
  tintsFrom,
} from "@/features/floorplan/lib/scene-cache"
import { STORE_DEPTH, STORE_WIDTH, ZONE_RECTS } from "@/features/floorplan/lib/store-model"
import type { ZoneId } from "@/features/floorplan/lib/zones"

const HALF_WIDTH = STORE_WIDTH / 2
const HALF_DEPTH = STORE_DEPTH / 2
const CONE_SEGMENTS = 20
const FIT_SPAN_X = 78
const FIT_SPAN_Y = 58
const TILE = 4
const skipRaycast: Object3D["raycast"] = () => undefined
function toColor(rgb: Rgb): Color {
  return new Color().setRGB(rgb[0], rgb[1], rgb[2], SRGBColorSpace)
}
function healthColor(palette: Palette, state: HealthState): Color {
  if (state === "online") {
    return toColor(palette.online)
  }
  if (state === "degraded") {
    return toColor(palette.degraded)
  }
  if (state === "offline") {
    return toColor(palette.offline)
  }
  return toColor(palette.unknown)
}
function tileGrid(): BufferGeometry {
  const points: number[] = []
  for (let x = TILE; x < STORE_WIDTH; x += TILE) {
    points.push(x - HALF_WIDTH, 0, -HALF_DEPTH, x - HALF_WIDTH, 0, HALF_DEPTH)
  }
  for (let y = TILE; y < STORE_DEPTH; y += TILE) {
    points.push(-HALF_WIDTH, 0, y - HALF_DEPTH, HALF_WIDTH, 0, y - HALF_DEPTH)
  }
  const geometry = new BufferGeometry()
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(points), 3))
  return geometry
}
function wedgePositions(placement: CameraPlacement): Float32Array {
  const half = (placement.fov * Math.PI) / 360
  const yaw = (placement.yaw * Math.PI) / 180
  const points: number[] = [0, 0, 0]
  for (let step = 0; step <= CONE_SEGMENTS; step += 1) {
    const angle = yaw - half + (2 * half * step) / CONE_SEGMENTS
    points.push(Math.sin(angle) * placement.range, 0, Math.cos(angle) * placement.range)
  }
  return new Float32Array(points)
}
function wedgeIndex(): Uint16Array {
  const indices: number[] = []
  for (let step = 1; step <= CONE_SEGMENTS; step += 1) {
    indices.push(0, step, step + 1)
  }
  return new Uint16Array(indices)
}
function FitCamera() {
  const camera = useThree((state) => state.camera)
  const size = useThree((state) => state.size)
  const invalidate = useThree((state) => state.invalidate)
  useEffect(() => {
    const zoom = Math.min(size.width / FIT_SPAN_X, size.height / FIT_SPAN_Y)
    camera.zoom = Math.max(3, zoom)
    camera.updateProjectionMatrix()
    invalidate()
  }, [camera, size, invalidate])
  return null
}
function Lighting() {
  return (
    <>
      <hemisphereLight intensity={0.75} groundColor="#4a4d55" />
      <ambientLight intensity={0.55} />
      <directionalLight position={[34, 50, 26]} intensity={1.35} />
      <directionalLight position={[-28, 24, -20]} intensity={0.4} />
    </>
  )
}
function ViewCone({
  placement,
  palette,
  state,
  selected,
  onSelect,
}: {
  placement: CameraPlacement
  palette: Palette
  state: HealthState
  selected: boolean
  onSelect: (cameraId: string) => void
}) {
  const positions = useMemo(() => wedgePositions(placement), [placement])
  const indices = useMemo(() => wedgeIndex(), [])
  const color = useMemo(() => healthColor(palette, state), [palette, state])
  const handleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      event.stopPropagation()
      onSelect(placement.cameraId)
    },
    [onSelect, placement.cameraId],
  )
  return (
    <group position={[placement.x - HALF_WIDTH, 0.06, placement.y - HALF_DEPTH]}>
      <mesh onClick={handleClick}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="index" args={[indices, 1]} />
        </bufferGeometry>
        <meshBasicMaterial
          color={color}
          transparent
          opacity={selected ? 0.4 : 0.2}
          depthWrite={false}
          side={2}
        />
      </mesh>
      <lineLoop raycast={skipRaycast}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={color} transparent opacity={selected ? 0.9 : 0.5} />
      </lineLoop>
    </group>
  )
}
function CameraMarker({
  placement,
  palette,
  state,
  selected,
  onSelect,
}: {
  placement: CameraPlacement
  palette: Palette
  state: HealthState
  selected: boolean
  onSelect: (cameraId: string) => void
}) {
  const color = useMemo(() => healthColor(palette, state), [palette, state])
  const handleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      event.stopPropagation()
      onSelect(placement.cameraId)
    },
    [onSelect, placement.cameraId],
  )
  return (
    <group
      position={[placement.x - HALF_WIDTH, placement.height, placement.y - HALF_DEPTH]}
      rotation={[0, (placement.yaw * Math.PI) / 180, 0]}
      onClick={handleClick}
    >
      <mesh scale={[1.1, 0.9, 1.7]}>
        <boxGeometry />
        <meshStandardMaterial color={color} roughness={0.5} />
      </mesh>
      <mesh position={[0, 0, 1.05]} scale={selected ? 0.6 : 0.42}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} />
      </mesh>
    </group>
  )
}
function ZoneLabels({ palette }: { palette: Palette }) {
  const invalidate = useThree((state) => state.invalidate)
  const fill = useMemo(() => cssRgb(palette.label), [palette])
  const [labels, setLabels] = useState<readonly LabelEntry[]>(() => peekLabels(fill) ?? [])
  useEffect(() => {
    const ready = peekLabels(fill)
    if (ready !== null) {
      setLabels(ready)
      invalidate()
      return
    }
    let cancelled = false
    void document.fonts.ready.then(() => {
      if (cancelled) {
        return
      }
      setLabels(cachedLabels(fill))
      invalidate()
    })
    return () => {
      cancelled = true
    }
  }, [fill, invalidate])
  return (
    <group>
      {labels.map((entry) => {
        const rect = ZONE_RECTS.find((item) => item.id === entry.id)
        if (rect === undefined) {
          return null
        }
        return (
          <mesh
            key={entry.id}
            raycast={skipRaycast}
            renderOrder={999}
            position={[rect.x + rect.w / 2 - HALF_WIDTH, 0.04, rect.y + rect.d / 2 - HALF_DEPTH]}
            rotation={[-Math.PI / 2, 0, 0]}
          >
            <planeGeometry args={[entry.width, LABEL_HEIGHT]} />
            <meshBasicMaterial
              map={entry.texture}
              transparent
              depthWrite={false}
              depthTest={false}
              opacity={0.9}
            />
          </mesh>
        )
      })}
    </group>
  )
}
function Zones({
  palette,
  hovered,
  activeZone,
  onHover,
  onSelectZone,
}: {
  palette: Palette
  hovered: ZoneId | null
  activeZone: ZoneId | null
  onHover: (zone: ZoneId | null) => void
  onSelectZone: (zone: ZoneId) => void
}) {
  const tint = useMemo(() => toColor(palette.zone), [palette])
  const active = useMemo(() => toColor(palette.zoneActive), [palette])
  return (
    <group>
      {ZONE_RECTS.map((rect) => {
        const isActive = rect.id === activeZone
        const isHovered = rect.id === hovered
        return (
          <mesh
            key={rect.id}
            position={[rect.x + rect.w / 2 - HALF_WIDTH, 0.03, rect.y + rect.d / 2 - HALF_DEPTH]}
            rotation={[-Math.PI / 2, 0, 0]}
            onPointerOver={(event: ThreeEvent<PointerEvent>) => {
              event.stopPropagation()
              onHover(rect.id)
            }}
            onPointerOut={() => {
              onHover(null)
            }}
            onClick={(event: ThreeEvent<MouseEvent>) => {
              event.stopPropagation()
              onSelectZone(rect.id)
            }}
          >
            <planeGeometry args={[rect.w, rect.d]} />
            <meshBasicMaterial
              color={isActive ? active : tint}
              transparent
              opacity={isActive ? 0.22 : isHovered ? 0.12 : 0}
              depthWrite={false}
            />
          </mesh>
        )
      })}
    </group>
  )
}
function Store({ palette }: { palette: Palette }) {
  const built = useMemo(
    () => cachedSolids(tintsFrom(toColor(palette.goods), toColor(palette.produce))),
    [palette],
  )
  const grid = useMemo(() => tileGrid(), [])
  const gridMaterial = useMemo(
    () =>
      new LineBasicMaterial({ color: toColor(palette.floorLine), transparent: true, opacity: 0.6 }),
    [palette],
  )
  const lineMaterial = useMemo(
    () => new LineBasicMaterial({ color: toColor(palette.edge), transparent: true, opacity: 0.75 }),
    [palette],
  )
  const materials = useMemo<Record<PartKind, MeshStandardMaterial>>(() => {
    const build = (rgb: Rgb, roughness: number): MeshStandardMaterial =>
      new MeshStandardMaterial({ color: toColor(rgb), roughness, metalness: 0 })
    const goods = new MeshStandardMaterial({ roughness: 0.72, metalness: 0 })
    goods.vertexColors = true
    return {
      wall: build(palette.wall, 0.95),
      wallCap: build(palette.wallCap, 0.95),
      partition: build(palette.partition, 0.95),
      partitionCap: build(palette.partitionCap, 0.95),
      storefront: build(palette.storefront, 0.14),
      storefrontFrame: build(palette.storefrontFrame, 0.6),
      frame: build(palette.frame, 0.72),
      deck: build(palette.deck, 0.78),
      goods,
      produce: build(palette.produce, 0.8),
      produceRim: build(palette.produceRim, 0.75),
      counterBody: build(palette.counterBody, 0.7),
      counterTop: build(palette.counterTop, 0.6),
      coolerBody: build(palette.coolerBody, 0.65),
      glass: build(palette.glass, 0.14),
      coolerFrame: build(palette.coolerFrame, 0.6),
      sign: build(palette.sign, 0.7),
      signPost: build(palette.signPost, 0.55),
      crate: build(palette.crate, 0.88),
      crateLid: build(palette.crateLid, 0.88),
    }
  }, [palette])
  useEffect(() => {
    return () => {
      grid.dispose()
      gridMaterial.dispose()
      lineMaterial.dispose()
      for (const material of Object.values(materials)) {
        material.dispose()
      }
    }
  }, [grid, gridMaterial, lineMaterial, materials])
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.06, 0]} raycast={skipRaycast}>
        <planeGeometry args={[STORE_WIDTH + 14, STORE_DEPTH + 14]} />
        <meshStandardMaterial color={toColor(palette.apron)} roughness={1} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} raycast={skipRaycast}>
        <planeGeometry args={[STORE_WIDTH, STORE_DEPTH]} />
        <meshStandardMaterial color={toColor(palette.floor)} roughness={0.95} />
      </mesh>
      <lineSegments
        geometry={grid}
        material={gridMaterial}
        position={[0, 0.01, 0]}
        raycast={skipRaycast}
      />
      {built.map((entry) => (
        <group
          key={entry.solid.id}
          position={[
            entry.solid.x + entry.solid.w / 2 - HALF_WIDTH,
            0,
            entry.solid.y + entry.solid.d / 2 - HALF_DEPTH,
          ]}
        >
          {entry.parts.parts.map((part) => (
            <mesh
              key={part.kind}
              geometry={part.geometry}
              material={materials[part.kind]}
              raycast={skipRaycast}
            />
          ))}
          {entry.parts.edges === null ? null : (
            <lineSegments
              geometry={entry.parts.edges}
              material={lineMaterial}
              raycast={skipRaycast}
            />
          )}
        </group>
      ))}
    </group>
  )
}
export function StoreScene({
  palette,
  health,
  selected,
  onSelect,
}: {
  palette: Palette
  health: Record<string, HealthState>
  selected: string | null
  onSelect: (cameraId: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const [awake, setAwake] = useState(true)
  const [hovered, setHovered] = useState<ZoneId | null>(null)
  const [generation, setGeneration] = useState(0)
  const onContextLost = useCallback((event: Event) => {
    event.preventDefault()
    dropSceneCache()
    setGeneration((current) => current + 1)
  }, [])
  useEffect(() => {
    return () => {
      dropSceneCache()
    }
  }, [])
  useEffect(() => {
    const node = container.current
    if (node === null) {
      return
    }
    let onScreen = true
    const sync = (): void => {
      setAwake(onScreen && document.visibilityState === "visible")
    }
    const observer = new IntersectionObserver((entries) => {
      const entry = entries[0]
      if (entry !== undefined) {
        onScreen = entry.isIntersecting
      }
      sync()
    })
    observer.observe(node)
    document.addEventListener("visibilitychange", sync)
    return () => {
      observer.disconnect()
      document.removeEventListener("visibilitychange", sync)
    }
  }, [])
  const activeZone = useMemo(() => {
    const match = PLACEMENTS.find((placement) => placement.cameraId === selected)
    return match === undefined ? null : match.zone
  }, [selected])
  const selectZone = useCallback(
    (zone: ZoneId) => {
      const match = PLACEMENTS.find((placement) => placement.zone === zone)
      if (match !== undefined) {
        onSelect(match.cameraId)
      }
    },
    [onSelect],
  )
  return (
    <div ref={container} className="aspect-[16/10] w-full">
      <Canvas
        key={generation}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener("webglcontextlost", onContextLost)
        }}
        flat
        dpr={[1, 2]}
        frameloop={awake ? "demand" : "never"}
        gl={{ antialias: true }}
        orthographic
        camera={{ position: [48, 42, 48], near: 0.1, far: 400, zoom: 10 }}
      >
        <Lighting />
        <Store palette={palette} />
        <ContactShadows
          position={[0, 0.02, 0]}
          scale={[STORE_WIDTH + 8, STORE_DEPTH + 8]}
          resolution={1024}
          frames={1}
          far={9}
          blur={2.6}
          opacity={0.34}
          color="#0b0d12"
        />
        <ZoneLabels palette={palette} />
        <Zones
          palette={palette}
          hovered={hovered}
          activeZone={activeZone}
          onHover={setHovered}
          onSelectZone={selectZone}
        />
        {PLACEMENTS.map((placement) => (
          <ViewCone
            key={`cone-${placement.cameraId}`}
            placement={placement}
            palette={palette}
            state={health[placement.cameraId] ?? "unknown"}
            selected={placement.cameraId === selected}
            onSelect={onSelect}
          />
        ))}
        {PLACEMENTS.map((placement) => (
          <CameraMarker
            key={`marker-${placement.cameraId}`}
            placement={placement}
            palette={palette}
            state={health[placement.cameraId] ?? "unknown"}
            selected={placement.cameraId === selected}
            onSelect={onSelect}
          />
        ))}
        <OrbitControls
          makeDefault
          enableDamping={false}
          enablePan={false}
          minZoom={4}
          maxZoom={44}
          minPolarAngle={0.25}
          maxPolarAngle={1.25}
        />
        <FitCamera />
      </Canvas>
    </div>
  )
}
