"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { api, type Schemas } from "@/lib/api/client";
import { isUnauthorized, unwrap } from "@/lib/api/errors";

export type Session = Schemas["SessionOut"];

export const meQueryKey = ["auth", "me"] as const;
export const loginMutationKey = ["auth", "login"] as const;

async function fetchMe(): Promise<Session | null> {
  try {
    return unwrap(await api.GET("/api/v1/auth/me"));
  } catch (error) {
    if (isUnauthorized(error)) return null;
    throw error;
  }
}

/**
 * The signed-in user. `data` is `null` when there is no valid session and `undefined`
 * while loading.
 */
export function useMe() {
  const query = useQuery({
    queryKey: meQueryKey,
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
  });
  // The server never knows the user. While a streamed segment hydrates, report "loading"
  // even if the client already has the user, so user-dependent markup matches the HTML.
  const hydrated = useHydrated();
  return hydrated ? query : { ...query, data: undefined, isSuccess: false, isPending: true as const };
}

const noopSubscribe = () => () => {};

/** False during server render and hydration, true afterwards. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: loginMutationKey,
    mutationFn: async (body: Schemas["LoginIn"]) => unwrap(await api.POST("/api/v1/auth/login", { body })),
    onSuccess: (session) => {
      queryClient.clear();
      queryClient.setQueryData(meQueryKey, session);
    },
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: async () => {
      const result = await api.POST("/api/v1/auth/logout");
      // An expired session is already signed out.
      if (!result.response.ok && result.response.status !== 401) unwrap(result);
    },
  });
}
