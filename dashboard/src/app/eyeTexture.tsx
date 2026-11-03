/**
 * Procedural eye texture and studio lighting. One sphere carries a procedural texture (pupil, fibrous
 * iris with crypts and collarette, limbal ring, veined sclera) with its pole
 * turned to face the viewer; a bulging, glossy cornea sits in front, lit by a
 * studio environment so it picks up real window reflections. Gaze follows the
 * pointer.
 */

import { useThree } from "@react-three/fiber";
import { useEffect } from "react";
import { CanvasTexture, PMREMGenerator, SRGBColorSpace } from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

const W = 2048;
const H = 1024; // rows map to polar angle: row 0 = the pole facing the viewer
const PUPIL = 0.17;
const IRIS = 0.43;
const LIMBUS = 0.045;

export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const hash = (x: number, y: number) => {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return s - Math.floor(s);
};
/** Smooth 2D value noise; x wraps every `period` cells so the seam is invisible. */
function noise(x: number, y: number, period: number) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const h = (a: number, b: number) => hash(((a % period) + period) % period, b);
  return (
    h(xi, yi) * (1 - u) * (1 - v) + h(xi + 1, yi) * u * (1 - v) +
    h(xi, yi + 1) * (1 - u) * v + h(xi + 1, yi + 1) * u * v
  );
}
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function buildTexture() {
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(W, H);
  const seed = Math.random() * 50;

  for (let y = 0; y < H; y++) {
    const theta = (y / H) * Math.PI;
    for (let x = 0; x < W; x++) {
      const a = (x / W) * Math.PI * 2;
      let R: number, G: number, B: number;

      if (theta < IRIS + LIMBUS) {
        const r = (theta - PUPIL) / (IRIS - PUPIL); // 0 at pupil edge, 1 at limbus
        if (theta < PUPIL) {
          R = 5; G = 6; B = 8;
        } else {
          // Radial fibres: stretched noise (long in r, fine in angle), two octaves.
          const fib =
            noise(x / 5 + seed, y / 22, W / 5) * 0.6 + noise(x / 2 + seed, y / 9, W / 2) * 0.4;
          // Crypts: soft dark pits clustered between collarette and limbus.
          const crypt = noise(x / 40 + seed, y / 14, W / 40);
          const pit = r > 0.35 && r < 0.9 ? clamp01((crypt - 0.5) * 1.6) * 0.3 : 0;
          // Colour: amber/brown near the pupil blending to green-teal outward.
          const t = clamp01((r - 0.2) / 0.55);
          R = lerp(176, 36, t); G = lerp(112, 104, t); B = lerp(42, 98, t);
          const k = 0.62 + 0.62 * fib - pit;
          // Collarette: a bright, wavy ring around 30% out.
          const wave = 0.3 + Math.sin(a * 9 + seed) * 0.015 + Math.sin(a * 23) * 0.006;
          const col = Math.exp(-Math.pow((r - wave) / 0.035, 2)) * 0.45;
          // Limbal ring: iris darkens toward its outer edge.
          const limb = r > 0.8 ? 1 - (r - 0.8) * 3.2 : 1;
          const ruff = r < 0.07 ? 0.35 + r * 9 : 1; // dark ruff at the pupil margin
          const m = k * (1 + col) * Math.max(0.12, limb) * ruff;
          R *= m; G *= m; B *= m;
          if (theta >= IRIS) { R = 12; G = 28; B = 34; }
        }
      } else {
        // Sclera: warm white, pinker and darker toward the rim, mottled slightly.
        const t = clamp01((theta - IRIS) / 1.5);
        const mott = noise(x / 40 + seed, y / 40, W / 40) * 14;
        R = lerp(250, 226, t * t) - mott * 0.3;
        G = lerp(246, 196, t * t) - mott * 0.5;
        B = lerp(240, 188, t * t) - mott * 0.6;
        // Soft shadow where the limbus meets the white.
        const edge = clamp01(1 - (theta - IRIS - LIMBUS) / 0.12);
        R *= 1 - edge * 0.25; G *= 1 - edge * 0.25; B *= 1 - edge * 0.2;
      }

      const i = (y * W + x) * 4;
      img.data[i] = R; img.data[i + 1] = G; img.data[i + 2] = B; img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  // Branching capillaries creeping in from the rim toward the iris.
  ctx.filter = "blur(0.7px)";
  ctx.lineCap = "round";
  const yStop = H * ((IRIS + LIMBUS + 0.1) / Math.PI);
  const vein = (x: number, y: number, w: number, depth: number) => {
    ctx.lineWidth = w;
    ctx.strokeStyle = `rgba(178,44,44,${0.12 + Math.random() * 0.2})`;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let s = 0; s < 22; s++) {
      x += (Math.random() - 0.5) * 26;
      y -= 6 + Math.random() * 8;
      if (y < yStop) break;
      ctx.lineTo(x, y);
      if (depth > 0 && Math.random() < 0.16) vein(x, y, w * 0.6, depth - 1);
    }
    ctx.stroke();
  };
  for (let n = 0; n < 110; n++) vein(Math.random() * W, H * (0.5 - Math.random() * 0.06), 1 + Math.random() * 1.8, 2);

  const tex = new CanvasTexture(c);
  tex.colorSpace = SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

/** Studio-style reflections for the cornea and wet sclera, no external HDR. */
export function Studio() {
  const { gl, scene } = useThree();
  useEffect(() => {
    const pmrem = new PMREMGenerator(gl);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = env;
    return () => {
      scene.environment = null;
      env.dispose();
      pmrem.dispose();
    };
  }, [gl, scene]);
  return null;
}

