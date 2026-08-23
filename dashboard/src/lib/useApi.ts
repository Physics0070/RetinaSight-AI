/**
 * Minimal data-fetching hooks.
 *
 * Deliberately small rather than pulling in a query library: the app needs
 * request/loading/error state and manual refetch, nothing more.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  refetch: () => void;
}

export function useQuery<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): QueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);

  // Keep the latest fetcher without making it a dependency, so callers can
  // pass an inline closure without causing an infinite loop.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setLoading(true);
    setError(null);

    fetcherRef
      .current(controller.signal)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((caught: unknown) => {
        if (!active || (caught as Error)?.name === "AbortError") return;
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError(0, "unexpected_error", "Something went wrong. Please try again."),
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  return { data, loading, error, refetch };
}

interface MutationState<TArgs extends unknown[], TResult> {
  run: (...args: TArgs) => Promise<TResult | null>;
  loading: boolean;
  error: ApiError | null;
  reset: () => void;
}

export function useMutation<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
): MutationState<TArgs, TResult> {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const actionRef = useRef(action);
  actionRef.current = action;

  const run = useCallback(async (...args: TArgs): Promise<TResult | null> => {
    setLoading(true);
    setError(null);
    try {
      return await actionRef.current(...args);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError(0, "unexpected_error", "Something went wrong. Please try again."),
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { run, loading, error, reset: () => setError(null) };
}
