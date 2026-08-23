/**
 * Connectivity awareness.
 *
 * Offline is a normal operating mode for this product, not an error. The UI
 * says what is happening and what will happen next — never a bare
 * "Network Error".
 */

import { useEffect, useState } from "react";

export function useConnectivity(): boolean {
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  return online;
}

export function ConnectivityBanner({ pendingCount }: { pendingCount?: number }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2.5 text-[var(--rs-text-xs)] lg:px-6"
      style={{
        borderColor: "color-mix(in srgb, var(--rs-warn) 40%, transparent)",
        background: "color-mix(in srgb, var(--rs-warn) 12%, transparent)",
      }}
    >
      <span
        className="font-bold uppercase tracking-[var(--rs-tracking-caps)]"
        style={{ color: "var(--rs-warn)" }}
      >
        Offline mode
      </span>
      <span style={{ color: "var(--rs-ink-muted)" }}>
        RetinaSight AI is continuing offline. Your screening data is stored
        securely on this device and will sync when connectivity returns.
      </span>
      {pendingCount !== undefined && pendingCount > 0 && (
        <span className="rs-numeric font-semibold" style={{ color: "var(--rs-ink)" }}>
          {pendingCount} item{pendingCount === 1 ? "" : "s"} waiting to sync
        </span>
      )}
    </div>
  );
}
