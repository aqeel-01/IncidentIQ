import { useEffect, useState } from "react";

import { getErrorMessage } from "@/api/errors";

type AsyncState<T> =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: T | null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: T | null; error: string };

type UseAsyncOptions = {
  enabled?: boolean;
  /** Keep the last successful result visible while refetching. */
  keepPreviousData?: boolean;
};

export function useAsync<T>(
  factory: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  options: UseAsyncOptions = {},
): AsyncState<T> & { reload: () => void } {
  const { enabled = true, keepPreviousData = false } = options;
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<AsyncState<T>>({
    status: enabled ? "loading" : "idle",
    data: null,
    error: null,
  });

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle", data: null, error: null });
      return;
    }

    const controller = new AbortController();
    setState((previous) => ({
      status: "loading",
      data: keepPreviousData ? previous.data : null,
      error: null,
    }));

    factory(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setState({ status: "success", data, error: null });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setState((previous) => ({
          status: "error",
          data: keepPreviousData ? previous.data : null,
          error: getErrorMessage(error),
        }));
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, keepPreviousData, tick, ...deps]);

  return {
    ...state,
    reload: () => setTick((value) => value + 1),
  };
}
