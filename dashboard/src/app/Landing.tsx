/**
 * Public front door: a scroll-driven film. One pinned WebGL canvas (the eye
 * pushes through the pupil into the retina, an AI heatmap lights its lesions,
 * then it pulls back to a result) with text chapters fading over it.
 * The 3D is lazy so sign-in never waits on three.js.
 */

import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

const EyeScene = lazy(() => import("./EyeScene"));

const SERIF = { fontFamily: "'Source Serif 4', ui-serif, Georgia, serif", fontWeight: 400 };
const CHAPTERS = 5;
const KICKER = "text-sm uppercase tracking-widest text-white/50";
const H2 = "text-4xl leading-tight md:text-6xl";

export function Landing() {
  const root = useRef<HTMLDivElement>(null);
  const progress = useRef(0);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const onScroll = () => {
      const span = (root.current?.offsetHeight ?? 0) - window.innerHeight;
      const p = span > 0 ? Math.min(1, Math.max(0, window.scrollY / span)) : 0;
      progress.current = p;
      setActive(Math.min(CHAPTERS - 1, Math.floor(p * CHAPTERS)));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const show = (i: number) => ({
    opacity: active === i ? 1 : 0,
    transform: `translateY(${active === i ? 0 : active > i ? -24 : 24}px)`,
    pointerEvents: active === i ? ("auto" as const) : ("none" as const),
    transition: "opacity 700ms ease, transform 700ms ease",
  });

  return (
    <div ref={root} className="relative bg-[#07090c] text-white" style={{ height: `${CHAPTERS * 100}vh` }}>
      <div className="sticky top-0 h-screen overflow-hidden">
        <Suspense fallback={null}>
          <div className="absolute inset-0">
            <EyeScene progress={progress} />
          </div>
        </Suspense>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(0,0,0,0.65))]" />

        <nav className="absolute inset-x-0 top-0 z-10 mx-auto flex max-w-[1200px] items-center justify-between px-6 py-6">
          <span className="text-lg font-medium">RetinaSight AI</span>
          <Link to="/login" className="rounded-full border border-white/70 px-5 py-2">
            Sign in
          </Link>
        </nav>

        <div className="absolute inset-0 mx-auto max-w-[1200px] px-6">
          <section className="absolute left-6 top-1/2 max-w-xl -translate-y-1/2" style={show(0)}>
            <h1 style={{ ...SERIF, letterSpacing: "-0.03em" }} className="text-5xl leading-[1.12] md:text-7xl">
              Catch diabetic eye disease <em>before</em> it steals sight.
            </h1>
            <p className="mt-6 max-w-md text-lg text-white/70">
              AI-assisted retinal screening for community clinics — explainable, and always
              reviewed by a clinician.
            </p>
            <p className="mt-10 text-sm text-white/50">Scroll ↓</p>
          </section>

          <section className="absolute bottom-24 left-6 max-w-xl" style={show(1)}>
            <p className={KICKER}>The problem</p>
            <h2 style={SERIF} className={H2}>About one in three people with diabetes develops retinopathy.</h2>
            <p className="mt-4 text-lg text-white/70">Most feel nothing until the damage is done.</p>
          </section>

          <section className="absolute bottom-24 left-6 max-w-xl" style={show(2)}>
            <p className={KICKER}>So we look inside</p>
            <h2 style={SERIF} className={H2}>A ten-second photo of the back of the eye.</h2>
            <p className="mt-4 text-lg text-white/70">Taken by a health worker, in the village, even offline.</p>
          </section>

          <section className="absolute bottom-24 left-6 max-w-xl" style={show(3)}>
            <p className={KICKER}>AI that shows its work</p>
            <h2 style={SERIF} className={H2}>The heatmap marks exactly where it found signs of disease.</h2>
            <p className="mt-4 text-lg text-white/70">
              Microaneurysms, exudates, haemorrhages — nothing hidden in a black box.
            </p>
          </section>

          <section className="absolute bottom-24 right-6 max-w-md md:top-1/2 md:bottom-auto md:-translate-y-1/2" style={show(4)}>
            <div className="rounded-3xl border border-white/15 bg-white/10 p-6 backdrop-blur">
              <p className="text-xs uppercase tracking-widest text-white/50">Example result · illustrative</p>
              <p style={SERIF} className="mt-2 text-3xl">Moderate NPDR</p>
              <p className="mt-1 text-white/70">Confidence 91% · Refer to an eye specialist</p>
            </div>
            <h2 style={SERIF} className="mt-6 text-3xl md:text-4xl">The decision stays human.</h2>
            <p className="mt-3 text-white/70">Every case reaches a doctor’s queue for review.</p>
            <Link to="/login" className="mt-6 inline-block rounded-full bg-white px-6 py-3 font-medium text-[#07090c]">
              Start screening
            </Link>
            <p className="mt-6 text-xs text-white/50">
              Screening support, not a diagnosis. Not clinically validated — demo data only.
            </p>
          </section>
        </div>

        <div className="absolute right-4 top-1/2 h-24 w-px -translate-y-1/2 bg-white/20" aria-hidden>
          <div className="w-px bg-white transition-all duration-700" style={{ height: `${((active + 1) / CHAPTERS) * 100}%` }} />
        </div>
      </div>
    </div>
  );
}
