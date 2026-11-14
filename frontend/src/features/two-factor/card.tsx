/** Two-factor on the Preferences tab (your own) and the workspace rule in the Team section. */
import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { sessionQuery, useWorkspace } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSaveSecurity, useSecurity } from "@/features/api4";
import { api, unwrap } from "@/lib/api";
import { Problem, RecoveryCodes, TwoFactorSetup } from "./setup";

type Open = null | "setup" | "codes" | "off";

export function TwoFactorCard() {
  const { user, session } = useWorkspace();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState<Open>(null);
  const [fresh, setFresh] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const close = () => { setOpen(null); setFresh(null); setError(null); };

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong. Try again."); }
    setBusy(false);
  }

  const newCodes = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const password = String(new FormData(e.currentTarget).get("password"));
    void run(async () => {
      setFresh(unwrap(await api.POST("/me/two-factor/recovery-codes", { body: { password } })).recovery_codes);
      void qc.invalidateQueries({ queryKey: sessionQuery.queryKey });
    });
  };

  const turnOff = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    void run(async () => {
      unwrap(await api.POST("/me/two-factor/disable", { body: { password: String(fd.get("password")), code: String(fd.get("code")) } }));
      toast.success("Two-factor turned off");
      close();
      void qc.invalidateQueries({ queryKey: ["team"] });
      const s = await qc.fetchQuery({ ...sessionQuery, staleTime: 0 });
      if (s.two_factor_setup_required) void navigate({ to: "/two-factor" });
    });
  };

  const left = user.recovery_codes_left;
  return (
    <section className="space-y-3 rounded-card border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 basis-64">
          <h2 className="flex items-center gap-2 font-semibold">Two-factor sign-in{user.two_factor && <span className="flex items-center gap-1 text-xs font-medium text-st-published"><ShieldCheck className="size-3.5" />On</span>}</h2>
          <p className="mt-1 text-sm text-ink-2">{user.two_factor
            ? "Signing in asks for your password and a code from your authenticator app."
            : "Add a second step to signing in: a 6-digit code from an authenticator app on your phone. A stolen password alone no longer opens your account."}</p>
        </div>
        {!user.two_factor && <Button variant="outline" onClick={() => setOpen("setup")}>Set up two-factor</Button>}
      </div>
      {user.two_factor && (
        <>
          <p className={left <= 2 ? "text-sm text-st-failed" : "text-sm"}>
            {left === 0 ? "No recovery codes left. Make new ones so a lost phone doesn't lock you out." : `${left} recovery ${left === 1 ? "code" : "codes"} left.`}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen("codes")}>New recovery codes</Button>
            <Button variant="outline" size="sm" onClick={() => setOpen("off")}>Turn off two-factor</Button>
          </div>
        </>
      )}

      {/* Clicking outside does not close these: the recovery codes are shown once. */}
      <Dialog open={open === "setup"} onOpenChange={(v) => !v && close()}>
        <DialogContent onInteractOutside={(e) => e.preventDefault()}>
          <DialogHeader><DialogTitle>Set up two-factor sign-in</DialogTitle></DialogHeader>
          {open === "setup" && <TwoFactorSetup onDone={close} />}
        </DialogContent>
      </Dialog>

      <Dialog open={open === "codes"} onOpenChange={(v) => !v && close()}>
        <DialogContent onInteractOutside={(e) => e.preventDefault()}>
          <DialogHeader><DialogTitle>New recovery codes</DialogTitle>{!fresh && <DialogDescription>Making new codes cancels the ones you have now.</DialogDescription>}</DialogHeader>
          {fresh ? <RecoveryCodes codes={fresh} intro="Your old codes no longer work. Save these now: they are shown this once."><Button onClick={close}>Done</Button></RecoveryCodes> : (
            <form className="space-y-4" onSubmit={newCodes}>
              <div className="space-y-1.5"><Label htmlFor="rc-password">Your password</Label><Input id="rc-password" name="password" type="password" required autoFocus autoComplete="current-password" /></div>
              <Problem>{error}</Problem>
              <DialogFooter><Button type="button" variant="ghost" onClick={close}>Cancel</Button><Button type="submit" disabled={busy}>Make new codes</Button></DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={open === "off"} onOpenChange={(v) => !v && close()}>
        <DialogContent>
          <DialogHeader><DialogTitle>Turn off two-factor sign-in</DialogTitle>
            <DialogDescription>{session.features.require_two_factor
              ? "This workspace requires two-factor, so you will be asked to set it up again straight away. Use this to move to a new phone."
              : "Your account will open with the password alone. Your recovery codes stop working."}</DialogDescription></DialogHeader>
          <form className="space-y-4" onSubmit={turnOff}>
            <div className="space-y-1.5"><Label htmlFor="off-password">Your password</Label><Input id="off-password" name="password" type="password" required autoFocus autoComplete="current-password" /></div>
            <div className="space-y-1.5"><Label htmlFor="off-code">Code from your authenticator app, or a recovery code</Label><Input id="off-code" name="code" required autoComplete="one-time-code" autoCapitalize="none" spellCheck={false} className="tnum max-w-[14rem]" /></div>
            <Problem>{error}</Problem>
            <DialogFooter><Button type="button" variant="ghost" onClick={close}>Cancel</Button><Button type="submit" variant="destructive" disabled={busy}>Turn off</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/** The workspace rule: everyone signs in with two-factor. Owners only. */
export function RequireTwoFactor() {
  const { data, isPending } = useSecurity();
  const save = useSaveSecurity();
  return (
    <label className="flex items-start gap-3 border-t border-line px-5 py-4 text-sm">
      <Switch checked={Boolean(data?.require_two_factor)} disabled={isPending || save.isPending} onCheckedChange={(v) => save.mutate({ require_two_factor: v })} />
      <span>Require two-factor for everyone
        <span className="block text-xs text-ink-2">Members without it are sent to set it up before they can do anything else. API tokens and assistants connected over MCP keep working.</span>
      </span>
    </label>
  );
}
