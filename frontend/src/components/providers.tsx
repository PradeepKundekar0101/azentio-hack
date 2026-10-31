"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, isUnauthorized } from "@/lib/api/errors";
import { loginMutationKey, meQueryKey } from "@/lib/auth/hooks";

function makeQueryClient() {
  // Any 401 from a data request means the session ended. Marking the user as signed out
  // lets the app shell's guard send them to /login (one place owns that redirect).
  const onError = (error: unknown) => {
    if (isUnauthorized(error)) client.setQueryData(meQueryKey, null);
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        // A 401 from login means wrong credentials, not an ended session.
        if (mutation.options.mutationKey?.join() === loginMutationKey.join()) return;
        onError(error);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
          return count < 2;
        },
      },
    },
  });
  return client;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        <Toaster position="bottom-right" />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
