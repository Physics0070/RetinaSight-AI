# UI design system

The interface should read as **retinal imaging + medical technology**, not as a
generic SaaS dashboard. Three ideas carry that:

1. **Futuristic clinical glass** — one coherent material across the product.
2. **Contextual density** — each role gets its own accent and information density.
3. **The retinal image is the subject.** Chrome recedes around it.

---

## The material

Every workspace is a deep vitreous ground with frosted, luminous panels floating
above it, edge-lit in the palette of retinal imaging: the amber-red of the fundus
and a diagnostic cyan for instrument readouts.

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
| **Health worker** | teal `#2ee6c5` | `#060d12` | highest contrast, largest controls — used outdoors, one-handed |
| **Doctor** | cyan `#22d3ee` | `#04060c` | darkest of the four; retinal images must be judged against darkness |
| **Patient** | warm amber `#ffa76b` | `#0d1018` | lightest, gentler blur, larger type — an anxious reader shouldn't decode an interface |
| **Admin** | indigo `#7c8cff` | `#070a13` | densest, monitoring-oriented |

One material, four densities. The work genuinely differs — a nurse in a field
clinic and a clinician at a workstation are not doing the same job — but they now
share one visual language.

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
`dashboard/src/test/contrast.test.tsx` — **30 tests** that compute real WCAG
ratios for every theme:

```
accent ink on accent fill        >= 4.5   (all five themes)
primary ink on the glass ground  >= 4.5
muted ink on the glass ground    >= 4.5
subtle ink (labels only)         >= 3.0
risk colours on the ground       >= 3.0
```

One test deliberately asserts that near-white on a bright accent **fails**, so
the reason the rule exists is documented alongside the fix.

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
