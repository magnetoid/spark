import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { sessionQuery } from "@/app/session";
import { api, setCsrfToken, unwrap } from "@/lib/api";
import { AuthFrame } from "@/pages/login";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SetupPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = unwrap(await api.POST("/auth/setup", { body: form }));
      setCsrfToken(s.csrf_token);
      qc.setQueryData(sessionQuery.queryKey, s);
      window.location.assign(import.meta.env.BASE_URL.replace(/\/$/, "") + "/brands/new");
    } catch {
      setError("Could not create the account. Use at least 8 characters for the password.");
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <AuthFrame title="Create the owner account">
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5"><Label htmlFor="name">Your name</Label><Input id="name" required value={form.name} onChange={set("name")} /></div>
        <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" required value={form.email} onChange={set("email")} /></div>
        <div className="space-y-1.5"><Label htmlFor="password">Password</Label><Input id="password" type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set("password")} /></div>
        {error && <p role="alert" className="text-sm text-st-failed">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating…" : "Create account"}</Button>
      </form>
    </AuthFrame>
  );
}
