"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

/**
 * Filter/sort/page state kept in the URL so views are linkable and survive reloads.
 * Values equal to their default are omitted from the URL.
 */
export function useUrlState<T extends Record<string, string>>(defaults: T) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const state = useMemo(() => {
    const out = { ...defaults };
    for (const key of Object.keys(defaults) as (keyof T)[]) {
      const v = searchParams.get(key as string);
      if (v !== null) out[key] = v as T[keyof T];
    }
    return out;
    // `defaults` is a module constant at call sites.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const update = useCallback(
    (patch: Partial<T>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === undefined || value === defaults[key]) params.delete(key);
        else params.set(key, value as string);
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [searchParams, router, pathname],
  );

  return [state, update] as const;
}

/**
 * Local editable copy of a value that can also change from outside (e.g. a URL filter).
 * Resets during render when the source changes, without an effect.
 */
export function useSyncedState(source: string) {
  const [draft, setDraft] = useState(source);
  const [prev, setPrev] = useState(source);
  if (source !== prev) {
    setPrev(source);
    setDraft(source);
  }
  return [draft, setDraft] as const;
}
