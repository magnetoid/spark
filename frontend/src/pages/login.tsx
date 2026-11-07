import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { sessionQuery, useSession } from "@/app/session";
import { api, ApiError, setCsrfToken, unwrap } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginPage() {
  const { data: session } = useSession();
  const { next } = useSearch({ from: "/login" });
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (session?.needs_setup) {
    void navigate({ to: "/setup" });
    return null;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = unwrap(await api.POST("/auth/login", { body: { email, password } }));
      setCsrfToken(s.csrf_token);
      qc.setQueryData(sessionQuery.queryKey, s);
      const target = next && next.startsWith("/") ? next : "/";
      window.location.assign(target.startsWith(import.meta.env.BASE_URL) ? target : import.meta.env.BASE_URL.replace(/\/$/, "") + target);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "That email and password don't match." : "Could not sign in. Try again.");
      setBusy(false);
    }
  }

  return (
    <AuthFrame title="Sign in to Spark">
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p role="alert" className="text-sm text-st-failed">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      </form>
    </AuthFrame>
  );
}

export function AuthFrame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-control bg-ink"><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden><path fill="#F2A516" d="M13 3 5 14h6l-1 7 8-11h-6z" /></svg></span>
          <span className="font-display text-lg font-semibold">Spark</span>
        </div>
        <h1 className="mb-4 text-2xl font-semibold">{title}</h1>
        <div className="rounded-card border border-line bg-surface p-5">{children}</div>
      </div>
    </div>
  );
}
