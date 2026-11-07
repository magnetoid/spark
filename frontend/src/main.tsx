import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeRouter } from "@/app/router";
import { readTheme, setTheme } from "@/app/session";
import { ApiError, setUnauthorizedHandler } from "@/lib/api";
import "@/styles/app.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: true,
      staleTime: 15_000,
    },
  },
});

const router = makeRouter(queryClient);
setTheme(readTheme());
setUnauthorizedHandler(() => {
  void queryClient.invalidateQueries({ queryKey: ["session"] });
  void router.navigate({ to: "/login", search: { next: window.location.pathname + window.location.search } });
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <RouterProvider router={router} />
        <Toaster position="bottom-right" richColors closeButton toastOptions={{ duration: 4000 }} />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
);
