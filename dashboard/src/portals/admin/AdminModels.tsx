/**
 * Model registry and lifecycle.
 *
 * Lifecycle: REGISTER → VALIDATE → DEPLOY → ACTIVE → DEPRECATE.
 *
 * The validation control deliberately requires evidence: marking a model
 * "clinically validated" without metrics is rejected by the backend, and this
 * form reflects that rather than working around it.
 */

import { useState } from "react";

import { PageHeader } from "@/app/PageHeader";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Panel,
  Select,
  Table,
  Td,
  Th,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useMutation, useQuery } from "@/lib/useApi";
import type { ModelMetadata, ModelStatus } from "@/lib/types";
import { formatDate } from "@/portals/worker/WorkerDashboard";

const LIFECYCLE = ["registered", "validating", "deployed", "active", "deprecated"];

export function AdminModels() {
  const [registering, setRegistering] = useState(false);

  const models = useQuery((signal) => api.get<ModelMetadata[]>("/models", undefined, signal), []);
  const status = useQuery(
    (signal) => api.get<ModelStatus>("/models/status", undefined, signal),
    [],
  );

  const setStatus = useMutation(async (modelId: string, next: string) => {
    await api.post(`/models/${modelId}/status`, { status: next });
    models.refetch();
    status.refetch();
  });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Model registry"
        subtitle="Registered screening models and their lifecycle state."
        actions={
          <Button variant="primary" onClick={() => setRegistering((v) => !v)}>
            {registering ? "Close" : "Register model"}
          </Button>
        }
      />

      {/* --- active model status --- */}
      {status.data && (
        <Panel className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="rs-label">Currently serving</h2>
            <div className="flex flex-wrap gap-2">
              <Badge tone={status.data.available ? "ok" : "danger"}>
                {status.data.available ? "Loaded" : "Model not available"}
              </Badge>
              {status.data.is_development_model && <Badge tone="warn">Development</Badge>}
              <Badge tone={status.data.clinically_validated ? "ok" : "warn"}>
                {status.data.clinically_validated
                  ? "Clinically validated"
                  : "Not clinically validated"}
              </Badge>
            </div>
          </div>

          <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Detail label="Version" value={status.data.model_version} />
            <Detail label="Framework" value={status.data.framework} />
            <Detail
              label="Input size"
              value={status.data.input_size.join(" × ")}
            />
            <Detail label="Grad-CAM" value={status.data.supports_gradcam ? "Supported" : "No"} />
          </dl>

          {Object.keys(status.data.validation_metrics).length === 0 ? (
            <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
              No validation metrics are recorded for this model. Performance
              figures are shown only when a real validation run has produced them.
            </p>
          ) : (
            <dl className="grid gap-3 sm:grid-cols-3">
              {Object.entries(status.data.validation_metrics).map(([key, value]) => (
                <Detail key={key} label={key} value={String(value)} />
              ))}
            </dl>
          )}
        </Panel>
      )}

      {registering && (
        <RegisterModelForm
          onRegistered={() => {
            setRegistering(false);
            models.refetch();
          }}
        />
      )}

      {models.loading && <LoadingState label="Loading models" />}
      {models.error && <ErrorState message={models.error.message} onRetry={models.refetch} />}
      {models.data?.length === 0 && (
        <EmptyState
          title="No models registered"
          description="The development placeholder is serving requests until a real model is registered."
        />
      )}

      {models.data && models.data.length > 0 && (
        <Panel padded={false}>
          <Table caption="Registered models">
            <thead>
              <tr>
                <Th>Model</Th>
                <Th>Version</Th>
                <Th>Framework</Th>
                <Th>Target</Th>
                <Th>Validation</Th>
                <Th>Status</Th>
                <Th>Registered</Th>
              </tr>
            </thead>
            <tbody>
              {models.data.map((model) => (
                <tr key={model.id}>
                  <Td>
                    <span className="font-semibold">{model.name}</span>
                  </Td>
                  <Td>
                    <span className="rs-numeric">{model.version}</span>
                  </Td>
                  <Td>{model.framework}</Td>
                  <Td>{model.deployment_target.replace(/_/g, " ")}</Td>
                  <Td>
                    <Badge tone={model.validation_status === "validated" ? "ok" : "warn"}>
                      {model.validation_status.replace(/_/g, " ")}
                    </Badge>
                  </Td>
                  <Td>
                    <Select
                      aria-label={`Lifecycle status for ${model.name}`}
                      value={model.status}
                      disabled={setStatus.loading}
                      onChange={(e) => void setStatus.run(model.id, e.target.value)}
                    >
                      {LIFECYCLE.map((state) => (
                        <option key={state} value={state}>
                          {state}
                        </option>
                      ))}
                    </Select>
                  </Td>
                  <Td>{formatDate(model.created_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}

      {setStatus.error && <ErrorState message={setStatus.error.message} />}
    </div>
  );
}

function RegisterModelForm({ onRegistered }: { onRegistered: () => void }) {
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [framework, setFramework] = useState("onnx");
  const [target, setTarget] = useState("cloud");
  const [architecture, setArchitecture] = useState("efficientnet_b0");
  const [modelPath, setModelPath] = useState("");

  const register = useMutation(async () => {
    await api.post("/models", {
      name: name.trim(),
      version: version.trim(),
      framework,
      deployment_target: target,
      architecture,
      model_path: modelPath.trim() || null,
      classes: ["no_dr", "mild", "moderate", "severe", "proliferative"],
    });
    onRegistered();
  });

  return (
    <Panel className="flex flex-col gap-4">
      <h2 className="rs-label">Register a model</h2>
      <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
        New models start as <strong>registered</strong> and{" "}
        <strong>not clinically validated</strong>.
      </p>

      <form
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
        onSubmit={(event) => {
          event.preventDefault();
          void register.run();
        }}
      >
        <Field label="Name" htmlFor="model-name" required>
          <Input id="model-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Version" htmlFor="model-version" required>
          <Input
            id="model-version"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            required
          />
        </Field>
        <Field label="Framework" htmlFor="model-framework">
          <Select
            id="model-framework"
            value={framework}
            onChange={(e) => setFramework(e.target.value)}
          >
            <option value="onnx">ONNX</option>
            <option value="pytorch">PyTorch</option>
            <option value="tflite">TensorFlow Lite</option>
            <option value="development">Development</option>
          </Select>
        </Field>
        <Field label="Deployment target" htmlFor="model-target">
          <Select id="model-target" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="cloud">Cloud</option>
            <option value="edge_onnx">Edge (ONNX)</option>
            <option value="edge_tflite">Edge (TF Lite)</option>
            <option value="development">Development</option>
          </Select>
        </Field>
        <Field label="Architecture" htmlFor="model-arch">
          <Select
            id="model-arch"
            value={architecture}
            onChange={(e) => setArchitecture(e.target.value)}
          >
            <option value="efficientnet_b0">EfficientNet-B0</option>
            <option value="efficientnet_b3">EfficientNet-B3</option>
            <option value="mobilenet_v3_large">MobileNet V3 Large</option>
            <option value="resnet18">ResNet-18</option>
            <option value="resnet50">ResNet-50</option>
          </Select>
        </Field>
        <Field
          label="Artefact path"
          htmlFor="model-path"
          hint="Relative to the configured model directory."
        >
          <Input
            id="model-path"
            value={modelPath}
            onChange={(e) => setModelPath(e.target.value)}
          />
        </Field>

        <div className="sm:col-span-2 xl:col-span-3">
          {register.error && <ErrorState message={register.error.message} />}
        </div>

        <div className="flex items-end">
          <Button type="submit" variant="primary" loading={register.loading}>
            Register
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="rs-label">{label.replace(/_/g, " ")}</dt>
      <dd className="rs-numeric text-[var(--rs-text-sm)]">{value}</dd>
    </div>
  );
}
