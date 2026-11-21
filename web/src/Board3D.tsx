// A simplified 3D view of a board (T-02): the real outline, pads, traces, vias and holes from
// circuit.json, with each part drawn as a box of an assumed height (no real 3D models).
import { useEffect, useMemo, useRef } from "react"
import * as THREE from "three"
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js"
import { board3d } from "./build"

const COPPER = 0xd4a13a
const LIFT = 0.02 // copper sits just above the board face so it isn't hidden in it

export function Board3D({ circuit }: { circuit: any[] }) {
  const host = useRef<HTMLDivElement>(null)
  const model = useMemo(() => board3d(circuit), [circuit])

  useEffect(() => {
    const el = host.current
    if (!el) return
    const width = el.clientWidth || 800, height = 560
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x1b1f24)
    const span = Math.max(model.board.width, model.board.height)
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, span * 20)
    camera.position.set(span * 0.6, span * 1.1, span * 1.2)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(window.devicePixelRatio)
    el.appendChild(renderer.domElement)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 0, 0)
    scene.add(new THREE.AmbientLight(0xffffff, 0.6))
    const sun = new THREE.DirectionalLight(0xffffff, 1.0)
    sun.position.set(span, span * 2, span)
    scene.add(sun)

    const t = model.board.thickness
    const top = t / 2, bottom = -t / 2
    const at = (x: number, y: number) => [x - model.board.x, -(y - model.board.y)] as const
    const box = (w: number, h: number, d: number, color: number, x: number, y: number, z: number, rot = 0) => {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), new THREE.MeshStandardMaterial({ color }))
      mesh.position.set(x, y, z)
      mesh.rotation.y = rot
      scene.add(mesh)
    }
    box(model.board.width, t, model.board.height, 0x1f6b3a, 0, 0, 0)
    for (const pad of model.pads) {
      const [x, z] = at(pad.x, pad.y)
      box(pad.width, 0.04, pad.height, COPPER, x, pad.layer === "bottom" ? bottom - LIFT : top + LIFT, z)
    }
    for (const tr of model.traces) {
      const [x1, z1] = at(...tr.from), [x2, z2] = at(...tr.to)
      const length = Math.hypot(x2 - x1, z2 - z1)
      if (length === 0) continue
      box(length, 0.035, tr.width, COPPER, (x1 + x2) / 2, tr.layer === "bottom" ? bottom - LIFT : top + LIFT,
        (z1 + z2) / 2, -Math.atan2(z2 - z1, x2 - x1))
    }
    const cylinder = (d: number, color: number, x: number, z: number) => {
      const mesh = new THREE.Mesh(new THREE.CylinderGeometry(d / 2, d / 2, t + 0.1, 24),
        new THREE.MeshStandardMaterial({ color }))
      mesh.position.set(x, 0, z)
      scene.add(mesh)
    }
    for (const via of model.vias) cylinder(via.diameter, COPPER, ...at(via.x, via.y))
    for (const hole of model.holes) cylinder(hole.diameter, COPPER, ...at(hole.x, hole.y))
    for (const part of model.parts) {
      const [x, z] = at(part.x, part.y)
      const face = part.layer === "bottom" ? bottom - part.tall / 2 : top + part.tall / 2
      box(part.width * 0.9, part.tall, part.height * 0.9, 0x2a2d33, x, face, z, (part.rotation * Math.PI) / 180)
    }

    // Follow the panel's width: the page can be resized, or first drawn while narrow.
    const fit = () => {
      const w = el.clientWidth || width
      camera.aspect = w / height
      camera.updateProjectionMatrix()
      renderer.setSize(w, height)
    }
    const resized = new ResizeObserver(fit)
    resized.observe(el)

    let frame = 0
    const draw = () => {
      controls.update()
      renderer.render(scene, camera)
      frame = requestAnimationFrame(draw)
    }
    draw()
    return () => {
      cancelAnimationFrame(frame)
      resized.disconnect()
      controls.dispose()
      renderer.dispose()
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh) { o.geometry.dispose(); (o.material as THREE.Material).dispose() }
      })
      el.removeChild(renderer.domElement)
    }
  }, [model])

  return (
    <div>
      <div className="viewer" ref={host} data-testid="board-3d" style={{ background: "#1b1f24" }} />
      <p className="muted">Simplified 3D: parts are boxes of assumed height, not real 3D models. The outline, pads,
        traces, vias and holes are the board's own.</p>
    </div>
  )
}
