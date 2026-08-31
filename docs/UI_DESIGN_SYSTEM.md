# UI design system

The interface should read as **retinal imaging + medical technology**, not as a
generic SaaS dashboard. Three ideas carry that:

1. **Soft neumorphism** — one coherent material across the product.
2. **Contextual density** — each role gets its own accent and information density.
3. **The retinal image is the subject.** Chrome recedes around it.

---

## The material

Every workspace is a **warm ivory paper ground** from which panels are extruded —
or into which controls are pressed — by a single paired soft shadow: a white
highlight top-left, a warm taupe shadow bottom-right. No translucency, no blur,
no border: depth comes entirely from the light. The defining rule of neumorphism
is that a panel is the **same colour as the ground**; only the shadow separates
them, which is what makes the whole surface read as one continuous material
rather than a stack of cards. The register is a clinician's room — beige and
paper tones, soft-charcoal ink, a muted medical blue for action.

The ground is near-neutral by design. A strongly tinted surround shifts the
apparent colour of whatever sits on it (simultaneous contrast), and what sits on
it here is a fundus photograph whose hue is part of the clinical judgement —
haemorrhages and exudates are read partly by colour. Imaging workstations
specify a neutral surround for exactly this reason. The chrome is light and
paper-warm, but imagery keeps its own deep, near-black stage — the fundus is
read against darkness even while the clinician's surround is calm ivory.

Two shadows build every surface — a light source top-left, a deeper shadow
bottom-right:

| Surface | How |
|---|---|
| **Raised panel** (`.rs-panel`) | `box-shadow: dark bottom-right, light top-left` — lifted out of the ground |
| **Pressed well** (`.rs-inset`) | the same pair, `inset` — sunk into the ground (inputs, readouts) |
| **Key** (`.rs-neu`) | raised at rest, swaps to the inset shadow on `:active` — a button that physically depresses |

```css
:root {
  --rs-neu-light: rgba(255, 255, 255, 0.9);    /* top-left white highlight */
  --rs-neu-dark:  rgba(174, 158, 128, 0.45);   /* warm taupe shadow */
}
.rs-panel {
  background: var(--rs-surface-raised);          /* == the ground colour */
  border-radius: var(--rs-radius-lg);
  box-shadow:
    6px 6px 14px var(--rs-neu-dark),
    -6px -6px 14px var(--rs-neu-light);
}
```

There is no gradient or grid behind the panels — a flat, uniform ground is what
lets the soft shadows read. (This system began as a frosted **glassmorphism** — translucent `backdrop-filter`
panels over a lit, gridded ground — then a dark neumorphism, and is now the light
ivory neumorphism above. Only the palette and material moved; the structure and
components are unchanged across all three.)

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
| **Health worker** | field blue `#2f66aa` | `#efe8d6` | warmer, brighter ground — used outdoors, one-handed |
| **Doctor** | navy `#3a6098` | `#eee9df` | cleanest ivory; the colour of medical trust |
| **Patient** | indigo `#5f6bb0` | `#f2ede2` | softest, lightest ground, larger type — an anxious reader shouldn't decode an interface |
| **Admin** | violet-indigo `#5a4f9e` | `#e9e4d8` | densest, monitoring-oriented |

One material, four densities. The work genuinely differs — a nurse in a field
clinic and a clinician at a workstation are not doing the same job — but they now
share one visual language.

### Accents must not resemble severity colours

The previous palette failed this and nobody noticed, because each colour was
defensible on its own: the health-worker accent `#2ee6c5` sat **3° of hue** from
the low-risk colour `#2dd4bf`, and the patient accent `#ffa76b` sat **3°** from
the high-risk colour `#fb923c`. Interface chrome that resembles a severity
signal invites a misread of the one signal that must never be misread.

Every accent now sits in the **blue-to-indigo arc**, at least **35°** from every
severity hue — the tightest actual margin is the field-worker blue against the
deepened low-risk teal, at ~42°. Blue reads as medical trust and, unlike a warm
bronze or gold, stays clear of the amber/orange severity band. The rule is
enforced by test, including a guard-the-guard case pinning the two historical
failures.

On the light ivory ground the severity colours themselves are **deepened** —
same learned hues (green → amber → orange → red), darker so they clear the
≥3.0 contrast bar on paper. That is a legibility requirement of the light
theme, not a restyle of a clinically load-bearing scale.

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

Low contrast is the main risk this design takes: a soft matte surface can quietly
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
primary ink on the matte ground   >= 4.5
muted ink on the matte ground     >= 4.5
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
- **Contrast is enforced by test**, because soft surfaces make it easy to break.

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
hierarchy · shadows so soft they cost legibility.
