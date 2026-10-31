"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Schemas } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

export type User = Schemas["UserOut"];
export type UserCreate = Schemas["UserCreate"];
export type UserPatch = Schemas["UserPatch"];

export const usersKey = ["users"] as const;

/** Every account, oldest first. Admin only; anyone else gets a 403 from the API. */
export function useUsers() {
  return useQuery({
    queryKey: usersKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/users")),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: UserCreate) => unwrap(await api.POST("/api/v1/users", { body })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: UserPatch & { id: number }) =>
      unwrap(await api.PATCH("/api/v1/users/{user_id}", { params: { path: { user_id: id } }, body })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}
