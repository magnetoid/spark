/**
 * Session and workspace state: who is signed in, which brands exist, which brand is
 * active, and the theme. The active brand lives in the URL (?brand=slug) so a link
 * always opens the right workspace, with localStorage as the fallback for bare URLs.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { api, setCsrfToken, unwrap } from "@/lib/api";
import type { components } from "@/api/schema";
import { applyBrandColor } from "@/lib/brand-color";

export type Session = components["schemas"]["SessionOut"];
export type Brand = components["schemas"]["BrandOut"];
export type User = components["schemas"]["UserOut"];

export const sessionQuery = {
  queryKey: ["session"] as const,
  queryFn: async () => {
    const s = unwrap(await api.GET("/session"));
    setCsrfToken(s.csrf_token);
    return s;
  },
  staleTime: 60_000,
};

export function useSession() {
  return useQuery(sessionQuery);
}

// ---- theme --------------------------------------------------------------------------
export type ThemeMode = "light" | "dark" | "system";
const THEME_KEY = "spark.theme";

export function readTheme(): ThemeMode {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function isDark(mode: ThemeMode) {
  return mode === "dark" || (mode === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
}

export function setTheme(mode: ThemeMode) {
  try {
    if (mode === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, mode);
  } catch { /* private mode: the choice just does not persist */ }
  document.documentElement.classList.toggle("dark", isDark(mode));
  window.dispatchEvent(new Event("spark:theme"));
}

// ---- active brand --------------------------------------------------------------------
const BRAND_KEY = "spark.brand";

interface WorkspaceValue {
  session: Session;
  user: User;
  brands: Brand[];
  brand: Brand | null;
  setBrand: (slug: string) => void;
  signOut: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ session, children }: { session: Session; children: ReactNode }) {
  const search = useSearch({ strict: false }) as { brand?: string };
  const navigate = useNavigate();
  const qc = useQueryClient();
  const brands = session.brands;

  const brand = useMemo(() => {
    let stored: string | null = null;
    try { stored = localStorage.getItem(BRAND_KEY); } catch { /* ignore */ }
    const wanted = search.brand ?? stored;
    return brands.find((b) => b.slug === wanted) ?? brands[0] ?? null;
  }, [brands, search.brand]);

  useEffect(() => {
    if (!brand) return;
    try { localStorage.setItem(BRAND_KEY, brand.slug); } catch { /* ignore */ }
    const paint = () => applyBrandColor(brand.color);
    paint();
    window.addEventListener("spark:theme", paint);
    return () => window.removeEventListener("spark:theme", paint);
  }, [brand]);

  const setBrand = useCallback((slug: string) => {
    void navigate({ to: ".", search: (prev) => ({ ...prev, brand: slug }) });
  }, [navigate]);

  const signOut = useCallback(async () => {
    unwrap(await api.POST("/auth/logout"));
    await qc.invalidateQueries({ queryKey: sessionQuery.queryKey });
    void navigate({ to: "/login" });
  }, [navigate, qc]);

  const value = useMemo<WorkspaceValue | null>(() => session.user ? {
    session, user: session.user, brands, brand, setBrand, signOut,
  } : null, [session, brands, brand, setBrand, signOut]);

  if (!value) return null;
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const v = useContext(WorkspaceContext);
  if (!v) throw new Error("useWorkspace outside of WorkspaceProvider");
  return v;
}

/** The active brand, or throws: pages under the shell always have one (the shell redirects otherwise). */
export function useBrand(): Brand {
  const { brand } = useWorkspace();
  if (!brand) throw new Error("No brand");
  return brand;
}
