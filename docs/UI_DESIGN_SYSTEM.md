# UI design system

The interface should read as **retinal imaging + medical technology**, not as a
generic SaaS dashboard. Two ideas carry that:

1. **Contextual morphism** — each role gets the material its work demands.
2. **The retinal image is the subject.** Chrome recedes around it.

---

## Tokens

Everything resolves to CSS custom properties in
`dashboard/src/design-system/tokens/tokens.css`. Components contain **no colour
literals**; Tailwind is a utility layer mapped onto the same tokens.

The palette comes from fundus photography itself — the deep vitreous dark, the
amber-red of the retina, and a clinical cyan for instrument readouts.

```css
--rs-retina: #c2410c;        /* fundus amber-red   */
--rs-retina-deep: #7c2d12;
--rs-vitreous: #0a0f16;      /* imaging ground     */
```

Role themes are switched by a `data-role` attribute on the document root, which
re-points the same token names. One component therefore renders correctly in all
four workspaces.

---

## Contextual morphism

| Role | Material | Why |
|---|---|---|
| **Health worker** | medical-device **neumorphism** — soft tactile surfaces, physical depth, large controls | used one-handed, outdoors, sometimes gloved; should feel like an instrument |
| **Doctor** | clinical **glassmorphism** on a dark imaging ground | retinal images must be judged against darkness, as on a lightbox or DICOM workstation |
| **Patient** | soft, calm surfaces, larger base type, minimal glass | anxious reader, low cognitive load, high legibility |
| **Admin** | structured command-centre glass over slate | dense, monitoring-oriented, information-first |

Glass is applied **only** in the dark themes, where it reads as instrument
chrome. In the light themes it would be decoration, so it is not used.

```css
[data-role="doctor"] .rs-panel,
[data-role="admin"] .rs-panel {
  backdrop-filter: blur(14px) saturate(1.25);
}
```

---

## Retinal image viewer

`design-system/medical-imaging/RetinalImageViewer.tsx` — the centrepiece of the
clinical workspace.

- Deep radial ground, never pure black — the standard for judging fundus imagery.
- Layers: **Original · Heat map · Overlay**, disabled when no explanation exists.
- Zoom (1×–6×), pan by pointer drag, fit-to-view.
- Side-by-side comparison of both eyes.
- Attention-region boxes with intensity labels.
- **Laterality is always visible** — "Left eye (OS)" / "Right eye (OD)" — because
  confusing eyes is a clinical error.
- The Grad-CAM caveat appears whenever an explanation layer is active.

Fully keyboard operable: arrows pan, `+`/`-` zoom, `0` resets. A mouse is never
required.

---

## Clinical risk — never colour alone

This is a safety requirement, not a preference. Severity is carried by **four
redundant channels**:

| Channel | Low | Moderate | High | Urgent |
|---|:--:|:--:|:--:|:--:|
| Glyph | ○ | ◐ | ◕ | ● |
| Label | "Low" | "Moderate" | "High" | "Urgent" |
| Position on the ordered scale | 1 | 2 | 3 | 4 |
| Colour | teal | amber | orange | red |

Colour is the **last** cue, so the interface stays readable with colour-vision
deficiency, in greyscale, and to a screen reader. Enforced by tests that assert
every level has a text label and a distinct glyph.

The scale exposes itself as `role="img"` with a description:
*"Risk level: Urgent. Urgent referral."*

### Confidence

Rendered as a segmented meter labelled **"model confidence"** — never as a bare
percentage that could be mistaken for a probability of disease. Missing
confidence shows "Not available" rather than a misleading zero.

---

## Standing clinical framing

Two components appear wherever AI output does:

- `AiAssistanceNotice` — *"AI-assisted screening support. This is not a
  diagnosis. A qualified clinician reviews every screening."*
- `DevelopmentModelBanner` — unmissable warning when output came from the
  placeholder model.

Both are tested for their exact wording, because vaguer phrasing would misrepresent
what the system does.

---

## Language register

The same clinical fact is worded differently per audience:

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

Never a raw exception, status code or stack trace. The API supplies a
human-readable message and the UI renders it directly:

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
| Scanning sweep | during the quality gate | work is happening |
| Progressive readouts | align / light / focus | live instrument feedback |
| Heatmap reveal | Grad-CAM | layer change |

All of it is suppressed under `prefers-reduced-motion`, and none of it is the
only channel carrying information.

---

## Accessibility

- Semantic HTML; `role` and `aria-*` only where semantics are insufficient.
- Visible focus rings everywhere, never removed.
- A skip link on every portal shell.
- Full keyboard operation, including the image viewer.
- Live regions for loading, offline and error states.
- **Severity never depends on colour alone.**

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
glass everywhere regardless of context · decorative blobs · a chatbot shell ·
uniform rounded-card grids with no hierarchy.
