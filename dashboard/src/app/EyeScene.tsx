/**
 * The film. Scroll progress (0..1, damped) drives one WebGL scene: the eye
 * turns toward the pointer, swells until the pupil fills the frame, a retina
 * fades up out of the dark, an AI heatmap lights its lesions, and the retina
 * settles aside for the result card.
 */

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import type { MutableRefObject } from "react";
import { CanvasTexture, SRGBColorSpace } from "three";
import type { Group, Mesh, MeshBasicMaterial } from "three";

import { Studio, buildTexture, clamp01 } from "./eyeTexture";

/* -------------------------------------------------------------------------- */
/* Fundus (the back of the eye) and its AI heatmap                             */
/* -------------------------------------------------------------------------- */

const F = 1024;
const MACULA: [number, number] = [410, 512];
const DISC: [number, number] = [700, 470];
// [x, y, radius]
const MICRO = [[380, 480, 4], [440, 470, 4], [395, 545, 5], [455, 520, 4], [360, 520, 4], [430, 560, 5]];
const EXUDATE = [[330, 470, 7], [345, 490, 6], [335, 510, 8], [480, 590, 8], [495, 600, 6]];
const HEMORRHAGE = [[400, 440, 16], [470, 540, 14], [300, 560, 12], [560, 420, 13]];
const HOT = [[390, 500, 120], [335, 490, 75], [480, 595, 65], [560, 420, 65], [300, 560, 60]];

function canvas2d() {
  const c = document.createElement("canvas");
  c.width = F;
  c.height = F;
  return { c, ctx: c.getContext("2d")! };
}
const asTexture = (c: HTMLCanvasElement) => {
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  t.anisotropy = 8;
  return t;
};

function dots(ctx: CanvasRenderingContext2D, list: number[][], fill: string) {
  ctx.fillStyle = fill;
  for (const [x, y, r] of list) {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 7);
    ctx.fill();
  }
}

function buildFundus() {
  const { c, ctx } = canvas2d();
  ctx.beginPath();
  ctx.arc(F / 2, F / 2, F / 2 - 4, 0, Math.PI * 2);
  ctx.clip();

  const bg = ctx.createRadialGradient(F * 0.45, F / 2, 40, F / 2, F / 2, F / 2);
  bg.addColorStop(0, "#e0702f");
  bg.addColorStop(0.55, "#b8421a");
  bg.addColorStop(1, "#4a1409");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, F, F);

  for (let n = 0; n < 90; n++) {
    ctx.fillStyle = `rgba(${Math.random() < 0.5 ? "120,30,10" : "240,140,60"},0.05)`;
    ctx.beginPath();
    ctx.arc(Math.random() * F, Math.random() * F, 20 + Math.random() * 60, 0, 7);
    ctx.fill();
  }

  const macula = ctx.createRadialGradient(MACULA[0], MACULA[1], 4, MACULA[0], MACULA[1], 70);
  macula.addColorStop(0, "rgba(90,20,8,0.75)");
  macula.addColorStop(1, "rgba(90,20,8,0)");
  ctx.fillStyle = macula;
  ctx.fillRect(0, 0, F, F);

  // Vessels: wandering, tapering strokes that fan out from the optic disc.
  ctx.lineCap = "round";
  const vessel = (x: number, y: number, angle: number, w: number, depth: number, pull: number) => {
    for (let step = 0; step < 36 && w > 0.6; step++) {
      const nx = x + Math.cos(angle) * 14;
      const ny = y + Math.sin(angle) * 14;
      ctx.strokeStyle = `rgba(70,8,6,${0.55 + w * 0.04})`;
      ctx.lineWidth = w;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(nx, ny);
      ctx.stroke();
      x = nx;
      y = ny;
      angle += (pull - angle) * 0.03 + (Math.random() - 0.5) * 0.18;
      w *= 0.985;
      if (depth > 0 && Math.random() < 0.07) {
        vessel(x, y, angle + (Math.random() < 0.5 ? 0.7 : -0.7), w * 0.62, depth - 1, pull);
      }
    }
  };
  for (const sign of [-1, 1]) {
    vessel(DISC[0], DISC[1], Math.PI + sign * 0.9, 9, 3, Math.PI); // arcades curving toward the macula
    vessel(DISC[0], DISC[1], Math.PI + sign * 0.5, 7, 3, Math.PI + sign * 0.35);
    vessel(DISC[0], DISC[1], sign * 0.9, 6, 2, sign * 1.4);
  }

  const disc = ctx.createRadialGradient(DISC[0], DISC[1], 6, DISC[0], DISC[1], 66);
  disc.addColorStop(0, "#fff6cf");
  disc.addColorStop(0.5, "#f6cf84");
  disc.addColorStop(1, "rgba(240,170,90,0)");
  ctx.fillStyle = disc;
  ctx.beginPath();
  ctx.arc(DISC[0], DISC[1], 66, 0, 7);
  ctx.fill();

  dots(ctx, HEMORRHAGE, "rgba(95,10,10,0.8)");
  dots(ctx, MICRO, "rgba(150,15,15,0.95)");
  dots(ctx, EXUDATE, "rgba(255,240,170,0.92)");

  // Vignette, like a real fundus camera.
  const vig = ctx.createRadialGradient(F / 2, F / 2, F * 0.32, F / 2, F / 2, F / 2);
  vig.addColorStop(0, "rgba(0,0,0,0)");
  vig.addColorStop(1, "rgba(0,0,0,0.75)");
  ctx.fillStyle = vig;
  ctx.fillRect(0, 0, F, F);
  return asTexture(c);
}

/** Grad-CAM-style heat: hot cores on the lesions, cooling outward. */
function buildHeat() {
  const { c, ctx } = canvas2d();
  ctx.globalCompositeOperation = "lighter";
  for (const [x, y, r] of HOT) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, "rgba(255,20,0,1)");
    g.addColorStop(0.5, "rgba(255,190,0,0.8)");
    g.addColorStop(1, "rgba(255,230,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  return asTexture(c);
}

/* -------------------------------------------------------------------------- */
/* The film                                                                    */
/* -------------------------------------------------------------------------- */

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const ease = (t: number) => t * t * (3 - 2 * t);
const seg = (p: number, a: number, b: number) => ease(clamp01((p - a) / (b - a)));

function Story({ progress }: { progress: MutableRefObject<number> }) {
  const eye = useRef<Group>(null);
  const gaze = useRef<Group>(null);
  const fundus = useRef<Group>(null);
  const fundusMat = useRef<MeshBasicMaterial>(null);
  const heatMat = useRef<MeshBasicMaterial>(null);
  const scan = useRef<Mesh>(null);
  const scanMat = useRef<MeshBasicMaterial>(null);
  const smooth = useRef(0);

  const eyeMap = useMemo(buildTexture, []);
  const fundusMap = useMemo(buildFundus, []);
  const heatMap = useMemo(buildHeat, []);

  useFrame((s, dt) => {
    smooth.current += (progress.current - smooth.current) * Math.min(1, dt * 3); // damped, so it feels filmic
    const p = smooth.current;
    const t = s.clock.elapsedTime;
    const wide = s.size.width > 768;
    const ease4 = Math.min(1, dt * 4);

    // Camera: gentle parallax with the pointer.
    s.camera.position.x += (s.pointer.x * 0.35 - s.camera.position.x) * Math.min(1, dt * 3);
    s.camera.position.y += (s.pointer.y * 0.2 - s.camera.position.y) * Math.min(1, dt * 3);
    s.camera.lookAt(0, 0, 0);

    // 1) Eye: hero on the right, centres, then swells until the pupil fills the frame.
    const grow = seg(p, 0.2, 0.42);
    const k = mix(1, 9, grow * grow);
    if (eye.current && gaze.current) {
      eye.current.visible = p < 0.45;
      eye.current.scale.setScalar(k);
      const settle = seg(p, 0, 0.2);
      eye.current.position.set(
        mix(wide ? 1.7 : 0, 0, settle),
        wide ? 0 : mix(-0.9, 0, settle),
        1.4 * (1 - grow) - 1.4 * k, // keeps the pupil on the camera axis as it grows
      );
      const look = 1 - grow;
      gaze.current.rotation.y += ((s.pointer.x * 0.6 + Math.sin(t * 0.4) * 0.08) * look - gaze.current.rotation.y) * ease4;
      gaze.current.rotation.x += ((-s.pointer.y * 0.4 + Math.cos(t * 0.5) * 0.05) * look - gaze.current.rotation.x) * ease4;
    }

    // 2) Retina fades up out of the dark, dollies in, then settles aside for the result.
    if (fundus.current && fundusMat.current && heatMat.current && scan.current && scanMat.current) {
      const aside = seg(p, 0.8, 0.95);
      fundusMat.current.opacity = seg(p, 0.4, 0.5);
      fundus.current.visible = p > 0.39;
      fundus.current.scale.setScalar(mix(1.3, 1, seg(p, 0.4, 0.62)) * (1 - 0.3 * aside));
      // Sits high while a chapter's text runs along the bottom, then moves aside for the result.
      fundus.current.position.set(wide ? -2.3 * aside : 0, 0.7 * (1 - aside) + (wide ? 0 : 0.5 * aside), -0.5);
      fundus.current.rotation.z = Math.sin(t * 0.3) * 0.03 + p * 0.25;
      scan.current.rotation.z = -fundus.current.rotation.z; // keep the scan line level
      heatMat.current.opacity = seg(p, 0.6, 0.72) * (0.9 + 0.1 * Math.sin(t * 3));
      scanMat.current.opacity = p > 0.5 && p < 0.62 ? 0.85 : 0;
      scan.current.position.y = mix(2.3, -2.3, seg(p, 0.5, 0.62));
    }
  });

  return (
    <>
      <group ref={eye}>
        <group ref={gaze}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <sphereGeometry args={[1.4, 160, 160]} />
            <meshPhysicalMaterial
              map={eyeMap}
              bumpMap={eyeMap}
              bumpScale={1.2}
              roughness={0.38}
              clearcoat={0.6}
              clearcoatRoughness={0.25}
              envMapIntensity={0.9}
            />
          </mesh>
          {/* Cornea: a clear dome bulging past the eyeball, glossy and wet. */}
          <mesh position={[0, 0, 0.72]}>
            <sphereGeometry args={[0.8, 96, 96]} />
            <meshPhysicalMaterial
              transparent
              opacity={0.12}
              roughness={0}
              clearcoat={1}
              clearcoatRoughness={0}
              ior={1.376}
              envMapIntensity={1.6}
              depthWrite={false}
            />
          </mesh>
        </group>
      </group>

      <group ref={fundus} visible={false} position={[0, 0, -0.5]}>
        <mesh>
          <planeGeometry args={[4.6, 4.6]} />
          <meshBasicMaterial ref={fundusMat} map={fundusMap} transparent opacity={0} />
        </mesh>
        <mesh position={[0, 0, 0.01]}>
          <planeGeometry args={[4.6, 4.6]} />
          <meshBasicMaterial ref={heatMat} map={heatMap} transparent opacity={0} depthWrite={false} />
        </mesh>
        <mesh ref={scan} position={[0, 2.3, 0.02]}>
          <planeGeometry args={[4.6, 0.025]} />
          <meshBasicMaterial ref={scanMat} color="#7ff0ff" transparent opacity={0} depthWrite={false} />
        </mesh>
      </group>
    </>
  );
}

export default function EyeScene({ progress }: { progress?: MutableRefObject<number> }) {
  const fallback = useRef(0);
  return (
    <Canvas camera={{ position: [0, 0, 6.6], fov: 40 }} dpr={[1, 2]} aria-hidden>
      <Studio />
      <ambientLight intensity={0.25} />
      <directionalLight position={[3, 4, 5]} intensity={1.6} />
      <pointLight position={[-4, 2, 4]} intensity={14} color="#ffd9c2" />
      <Story progress={progress ?? fallback} />
    </Canvas>
  );
}
