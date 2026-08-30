/**
 * Workflow UI: capture instrument feedback, offline messaging, error states
 * and the retinal viewer's clinical controls.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConnectivityBanner } from "@/app/Connectivity";
import { EmptyState, ErrorState, Metric } from "@/design-system/components/primitives";
import { RetinalImageViewer } from "@/design-system/medical-imaging/RetinalImageViewer";
import { CaptureInstrument } from "@/portals/worker/CaptureInstrument";
import { ScreeningStateChip, stateLabel } from "@/portals/worker/ScreeningStateChip";
import type { QualityAssessment } from "@/lib/types";

function quality(overrides: Partial<QualityAssessment> = {}): QualityAssessment {
  return {
    id: "q1",
    image_id: "i1",
    session_id: "s1",
    is_acceptable: true,
    result: "acceptable",
    overall_score: 0.81,
    blur_score: 0.78,
    lighting_score: 0.83,
    framing_score: 0.8,
    retinal_visibility_score: 0.85,
    issues: [],
    recommendations: [],
    assessed_on_device: false,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("capture instrument", () => {
  it("presents an alignment target rather than a bare file picker", () => {
    render(
      <CaptureInstrument
        eyeSide="left"
        onCapture={vi.fn()}
        analysing={false}
        quality={null}
        onRetake={vi.fn()}
      />,
    );

    expect(screen.getByText(/align the lens with the pupil/i)).toBeInTheDocument();
    expect(screen.getByText(/^Align$/)).toBeInTheDocument();
    expect(screen.getByText(/^Light$/)).toBeInTheDocument();
    expect(screen.getByText(/^Focus$/)).toBeInTheDocument();
  });

  it("labels which eye is being captured", () => {
    render(
      <CaptureInstrument
        eyeSide="right"
        onCapture={vi.fn()}
        analysing={false}
        quality={null}
        onRetake={vi.fn()}
      />,
    );
    expect(screen.getAllByText(/right eye \(OD\)/i).length).toBeGreaterThan(0);
  });

  it("explains what to fix when the quality gate rejects an image", () => {
    render(
      <CaptureInstrument
        eyeSide="left"
        onCapture={vi.fn()}
        analysing={false}
        quality={quality({
          is_acceptable: false,
          result: "retake_required",
          blur_score: 0.2,
          issues: ["blur"],
          recommendations: ["Hold the phone steady and let the camera focus."],
        })}
        onRetake={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/not suitable for analysis/i);
    expect(screen.getByText(/hold the phone steady/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retake/i })).toBeInTheDocument();
  });

  it("confirms acceptance with the achieved score", () => {
    render(
      <CaptureInstrument
        eyeSide="left"
        onCapture={vi.fn()}
        analysing={false}
        quality={quality()}
        accepted
        onRetake={vi.fn()}
      />,
    );
    expect(screen.getByText(/image quality accepted/i)).toBeInTheDocument();
  });

  it("offers zoom and fit controls only after an image is captured", async () => {
    // jsdom has no object-URL implementation; the component only needs a token.
    (URL as unknown as { createObjectURL: () => string }).createObjectURL = vi.fn(
      () => "blob:preview",
    );
    (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = vi.fn();

    render(
      <CaptureInstrument
        eyeSide="left"
        onCapture={vi.fn().mockResolvedValue(undefined)}
        analysing={false}
        quality={null}
        onRetake={vi.fn()}
      />,
    );

    // Nothing to frame yet, so no zoom controls before capture.
    expect(screen.queryByRole("button", { name: /zoom in/i })).not.toBeInTheDocument();

    const input = screen.getByLabelText(/capture retinal image for left eye/i);
    await userEvent.upload(input, new File(["x"], "eye.png", { type: "image/png" }));

    // Once captured, the operator can fit the fundus in the reticle.
    expect(screen.getByRole("button", { name: /zoom in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /fit to view/i })).toBeInTheDocument();
    expect(screen.getByText(/reposition/i)).toBeInTheDocument();
  });
});

describe("offline experience", () => {
  it("explains offline mode instead of showing a network error", () => {
    render(<ConnectivityBanner pendingCount={3} />);

    expect(screen.getByRole("status")).toHaveTextContent(/offline mode/i);
    expect(screen.getByText(/stored securely on this device/i)).toBeInTheDocument();
    expect(screen.getByText(/3 items waiting to sync/i)).toBeInTheDocument();
    expect(screen.queryByText(/network error/i)).not.toBeInTheDocument();
  });

  it("never surfaces raw technical failure text", () => {
    render(
      <ErrorState
        message="We could not complete the screening. Your image is saved on this device."
        onRetry={vi.fn()}
      />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/saved on this device/i);
    expect(alert.textContent).not.toMatch(/AxiosError|500|Traceback|undefined/);
  });

  it("offers a retry path when a request fails", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Something went wrong." onRetry={onRetry} />);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("retinal image viewer", () => {
  const image = {
    eyeSide: "left" as const,
    originalUrl: "blob:original",
    heatmapUrl: "blob:heatmap",
    overlayUrl: "blob:overlay",
    affectedRegions: [
      {
        region: "central",
        intensity: 0.8,
        bounds: { x: 0.33, y: 0.33, width: 0.33, height: 0.33 },
      },
    ],
  };

  it("offers original, heat map and overlay layers", () => {
    render(<RetinalImageViewer image={image} />);

    expect(screen.getByRole("button", { name: /^original$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /heat map/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^overlay$/i })).toBeInTheDocument();
  });

  it("provides zoom and fit controls", () => {
    render(<RetinalImageViewer image={image} />);

    expect(screen.getByRole("button", { name: /zoom in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /fit to view/i })).toBeInTheDocument();
  });

  it("is keyboard operable, not mouse-only", () => {
    render(<RetinalImageViewer image={image} />);

    const stage = screen.getByRole("group", { name: /retinal image/i });
    expect(stage).toHaveAttribute("tabIndex", "0");
    expect(stage).toHaveAccessibleName(/arrow keys to pan/i);
  });

  it("shows the Grad-CAM caveat when an explanation layer is active", async () => {
    render(<RetinalImageViewer image={image} />);

    await userEvent.click(screen.getByRole("button", { name: /heat map/i }));

    expect(screen.getByText(/not a validated lesion detector/i)).toBeInTheDocument();
  });

  it("disables explanation layers when no heatmap exists", () => {
    render(
      <RetinalImageViewer
        image={{
          eyeSide: "right",
          originalUrl: "blob:o",
          heatmapUrl: null,
          overlayUrl: null,
        }}
      />,
    );

    expect(screen.getByRole("button", { name: /heat map/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^overlay$/i })).toBeDisabled();
  });

  it("labels the eye so a clinician cannot confuse laterality", () => {
    render(<RetinalImageViewer image={image} />);
    expect(screen.getAllByText(/left eye \(OS\)/i).length).toBeGreaterThan(0);
  });
});

describe("workflow state presentation", () => {
  it("pairs every state with a readable label", () => {
    for (const state of [
      "retake_required",
      "ready_for_inference",
      "doctor_review",
      "completed",
    ]) {
      render(<ScreeningStateChip state={state} />);
      expect(stateLabel(state)).toBeTruthy();
      expect(stateLabel(state)).not.toContain("_");
    }
  });

  it("degrades gracefully for an unrecognised state", () => {
    expect(stateLabel("some_new_state")).toBe("some new state");
  });
});

describe("shared primitives", () => {
  it("renders an empty state with guidance", () => {
    render(<EmptyState title="No screenings yet" description="They will appear here." />);
    expect(screen.getByText(/no screenings yet/i)).toBeInTheDocument();
  });

  it("renders a metric with its label and value", () => {
    render(<Metric label="Pending reviews" value={7} />);
    expect(screen.getByText(/pending reviews/i)).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });
});
