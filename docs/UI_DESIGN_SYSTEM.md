# UI design system

The interface should read as **retinal imaging + medical technology**, not as a
generic SaaS dashboard. Three ideas carry that:

1. **Futuristic clinical glass** — one coherent material across the product.
2. **Contextual density** — each role gets its own accent and information density.
3. **The retinal image is the subject.** Chrome recedes around it.

---

## The material

Every workspace is a **neutral graphite** ground with frosted, luminous panels
floating above it, edge-lit by a role accent from the blue-violet arc.

The ground is near-neutral by design. A strongly tinted surround shifts the
apparent colour of whatever sits on it (simultaneous contrast), and what sits on
it here is a fundus photograph whose hue is part of the clinical judgement —
haemorrhages and exudates are read partly by colour. Imaging workstations
specify a neutral surround for exactly this reason. An earlier version of this
system used a navy ground; the colour identity now lives entirely in the chrome,
where it costs the image nothing.

Three layers build the depth:

| Layer | What it does |
|---|---|
| **Ambient light** (`body::before`) | fixed radial gradients — the light source the glass refracts |
| **Grid** (`body::after`) | a faint 56px lattice, masked to fade out, so blur has something to work on |
| **Glass panels** (`.rs-panel`) | `backdrop-filter: blur() saturate()` + a specular top edge |

The ambient layer is `position: fixed`, so glass moves across a *stationary*
light source as the page scrolls. That is what makes the depth read as physical
rather than painted on.

The specular sheen is a 1px gradient border drawn with a mask-composite trick —
a real pane of glass catches light along its top edge, and without it the panels
look like flat translucent rectangles.

```css
.rs-panel {
  background: var(--rs-surface-raised);   /* translucent */
  border: 1px solid var(--rs-line);
  backdrop-filter: blur(var(--rs-glass-blur)) saturate(var(--rs-glass-saturate));
  box-shadow: var(--rs-glass-edge), var(--rs-glass-inner), 0 10px 30px …;
}
```

---

## Tokens

Everything resolves to CSS custom properties in
`dashboard/src/design-system/tokens/tokens.css`. Components contain **no colour
literals**; Tailwind is a utility layer mapped onto the same tokens.

Role themes switch via a `data-role` attribute on the document root, which
re-points the same token names — so one component renders correctly in all four
workspaces.

| Role | Accent | Ground | Character |
|---|---|---|---|
| **Health worker** | lime `#a3e635` | `#0a0c0a` | highest contrast, largest controls — used outdoors, one-handed |
| **Doctor** | periwinkle `#7aa2ff` | `#070709` | darkest of the four; retinal images must be judged against darkness |
| **Patient** | lilac `#c9b6f7` | `#121116` | lightest, gentler blur, larger type — an anxious reader shouldn't decode an interface |
| **Admin** | orchid `#e879f9` | `#0c0a11` | densest, monitoring-oriented |

One material, four densities. The work genuinely differs — a nurse in a field
clinic and a clinician at a workstation are not doing the same job — but they now
share one visual language.

### Accents must not resemble severity colours

The previous palette failed this and nobody noticed, because each colour was
defensible on its own: the health-worker accent `#2ee6c5` sat **3° of hue** from
the low-risk colour `#2dd4bf`, and the patient accent `#ffa76b` sat **3°** from
the high-risk colour `#fb923c`. Interface chrome that resembles a severity
signal invites a misread of the one signal that must never be misread.

Every accent now sits at least **35°** from every severity hue — the tightest
actual margin is the field role's lime against moderate amber, at 39°. Lime is
the one accent outside the blue-violet arc, deliberately: at equal saturation it
carries the highest luminance of any hue, which is what survives direct sunlight
on a phone screen, and daylight legibility outranks palette symmetry for that
role. The rule is enforced by test, including a guard-the-guard case pinning the
two historical failures.

### A bug this palette work uncovered

`body` declared `transition: background`. When a transitioned property draws its
value from a custom property that changes — which is exactly how `data-role`
swaps a theme — Chrome latches the *previous* computed value and never
re-resolves it. Measured in the browser, the background was still on the
outgoing role's colour a full second later, not merely for the transition
duration.

The effect was that every portal painted on the `:root` ground, so the four
per-role grounds above had been written but never actually shipped. Removing the
transition makes them apply; role changes only happen on sign-in and sign-out,
so there was nothing worth cross-fading anyway.

---

## Contrast is a hard constraint, not a preference

Translucency is the main risk this design takes: a frosted panel can quietly
destroy legibility, and the failure is invisible in review because the colours
all *look* deliberate.

**A real bug shipped and was caught only by measuring in the browser.** The
primary button used the Tailwind arbitrary class `text-[var(--rs-accent-ink)]`.
That syntax is ambiguous between colour and font-size, so Tailwind never emitted
the rule; the button inherited near-white body ink and rendered white-on-cyan at
a contrast ratio of **1.58** — unreadable.

Fixed by setting the colour inline, and pinned by
`dashboard/src/test/contrast.test.tsx` — **43 tests** that compute real WCAG
ratios for every theme:

```
accent ink on accent fill        >= 4.5   (all five themes)
primary ink on the glass ground  >= 4.5
muted ink on the glass ground    >= 4.5
subtle ink (labels only)         >= 3.0
risk colours on every ground     >= 3.0
accent-to-severity hue distance  >= 35 degrees
```

**The suite parses `tokens.css` itself.** It previously kept a hand-copied table
of the palette, which meant a colour change could pass a green suite while
shipping unreadable colour — the tests would have been measuring the copy, not
the product. Reading the shipped stylesheet closes that gap.

Two tests exist to document *why* the rules exist rather than only asserting the
fix: one asserts that near-white on a bright accent **fails**, and one asserts
that the two historical accent/severity pairs **fail** the separation rule, so a
broken hue calculation cannot make the real check pass vacuously.

> Tried and rejected: importing the stylesheet with Vite's `?raw` suffix. Under
> vitest it resolves to `undefined`, which silently produced an empty palette —
> every contrast test would have passed by measuring nothing at all.

---

## Retinal image viewer

`design-system/medical-imaging/RetinalImageViewer.tsx` — the centrepiece.

- Deep radial ground, never pure black — the standard for judging fundus imagery.
- Layers: **Original · Heat map · Overlay**, disabled when no explanation exists.
- Zoom (1×–6×), pointer-drag pan, fit-to-view, side-by-side comparison.
- Attention-region boxes with intensity labels.
- **Laterality always visible** — "Left eye (OS)" / "Right eye (OD)". Confusing
  eyes is a clinical error.
- The Grad-CAM caveat appears whenever an explanation layer is active.

Fully keyboard operable: arrows pan, `+`/`-` zoom, `0` resets. A mouse is never
required.

---

## Clinical risk — never colour alone

A safety requirement, not a preference. Severity is carried by **four redundant
channels**:

| Channel | Low | Moderate | High | Urgent |
|---|:--:|:--:|:--:|:--:|
| Glyph | ○ | ◐ | ◕ | ● |
| Label | "Low" | "Moderate" | "High" | "Urgent" |
| Position on the ordered scale | 1 | 2 | 3 | 4 |
| Colour | teal | amber | orange | rose |

Colour is the **last** cue, so the interface stays readable with colour-vision
deficiency, in greyscale, and to a screen reader. The scale exposes itself as
`role="img"` with a description: *"Risk level: Urgent. Urgent referral."*

### Confidence

A segmented meter labelled **"model confidence"** — never a bare percentage that
could be mistaken for a probability of disease. Missing confidence shows "Not
available" rather than a misleading zero.

---

## Standing clinical framing

Two components appear wherever AI output does:

- `AiAssistanceNotice` — *"AI-assisted screening support. This is not a
  diagnosis. A qualified clinician reviews every screening."*
- `DevelopmentModelBanner` — unmissable warning when output came from the
  placeholder model.

Both are tested for their exact wording; vaguer phrasing would misrepresent what
the system does.

---

## Language register

The same clinical fact, worded for its audience:

| Category | Clinician | Patient |
|---|---|---|
| `no_dr` | No DR detected | No signs were found in this screening |
| `mild` | Mild NPDR | Early signs were found |
| `moderate` | Moderate NPDR | Some changes were found |
| `severe` | Severe NPDR | Significant changes were found |
| `proliferative` | Proliferative DR | Advanced changes were found |

A test asserts patient-facing strings contain **no** clinical abbreviations. The
patient portal also never shows model internals, confidence percentages, or the
word "diagnosis".

---

## Error and offline states

Never a raw exception, status code or stack trace:

```
We couldn't complete the screening.
Your captured image is safely stored on this device.

[ Try again ]   [ Save & exit ]
```

Offline is presented as a **mode**, not a failure:

```
OFFLINE MODE
RetinaSight AI is continuing offline. Your screening data is stored securely
on this device and will synchronise when connectivity returns.
3 items waiting to sync.
```

---

## Motion

Purposeful only:

| Animation | Where | Meaning |
|---|---|---|
| Ambient drift | background | 18s opacity breath — keeps a mostly-dark screen from feeling dead |
| Panel reveal | on mount | 6px rise, one frame of orientation |
| Scanning sweep | during the quality gate | work is happening |
| Progressive readouts | align / light / focus | live instrument feedback |
| Hover lift | interactive panels | 2px rise + accent edge |

All suppressed under `prefers-reduced-motion`, and none of it is the only
channel carrying information.

---

## Accessibility

- Semantic HTML; `role`/`aria-*` only where semantics are insufficient.
- Visible focus rings everywhere, never removed.
- A skip link on every portal shell.
- Full keyboard operation, including the image viewer.
- Live regions for loading, offline and error states.
- **Severity never depends on colour alone.**
- **Contrast is enforced by test**, because glass makes it easy to break.

---

## Responsiveness

Designed per role rather than by shrinking one layout:

| Role | Primary target | Navigation |
|---|---|---|
| Patient | mobile | bottom bar |
| Health worker | mobile / tablet | bottom bar on small screens |
| Doctor | desktop / tablet | sidebar |
| Admin | desktop | sidebar |

---

## Deliberately avoided

Generic admin templates · the default SaaS blue · purple "AI" gradients ·
decorative blobs · a chatbot shell · uniform rounded-card grids with no
hierarchy · glass so heavy it costs legibility.
