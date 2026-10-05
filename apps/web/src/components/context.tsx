"use client";
import { createContext, useContext, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import type { Me, Overview } from "@/lib/types";
export const AppContext = createContext<{
  me: Me;
  data: Overview;
  household: string;
  month: string;
  notify: (text: string) => void;
}>({} as never);
export function useApp() {
  return useContext(AppContext);
}
export function useCommand() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef("");
  const inFlight = useRef(false);
  const query = useQueryClient();
  const router = useRouter();
  const { notify } = useApp();
  async function run<T>(
    operation: (key: string) => Promise<T>,
    message = "Zapisano",
    after?: (result: T) => void,
  ) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    if (!key.current) key.current = crypto.randomUUID();
    try {
      const result = await operation(key.current);
      key.current = "";
      await query.invalidateQueries();
      if (notify) notify(message);
      after?.(result);
      return result;
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Nie udało się zapisać. Spróbuj ponownie.",
      );
      if (error instanceof ApiError && error.status === 401) router.push("/");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return { busy, error, run, setError };
}
