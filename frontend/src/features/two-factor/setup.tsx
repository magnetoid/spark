/**
 * Two-factor sign-in, the part a person does once: confirm the password, scan the QR code with
 * an authenticator app, type the first code, save the recovery codes. Used on the Preferences
 * tab and on the screen people land on when the workspace requires two-factor.
 */
import { useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { Copy, Download } from "lucide-react";
import { toast } from "sonner";
import { sessionQuery } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, unwrap } from "@/lib/api";

type Step = { at: "password" } | { at: "scan"; secret: string; uri: string } | { at: "codes"; codes: string[] };

/** The secret in groups of four, the way authenticator apps show it when typed by hand. */
export const groupSecret = (secret: string) => secret.replace(/(.{4})(?=.)/g, "$1 ");

export function TwoFactorSetup({ onDone, doneLabel = "Done" }: { onDone: () => void; doneLabel?: string }) {
  const qc = useQueryClient();
  const [step, setStep] = useState<Step>({ at: "password" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong. Try again."); }
    setBusy(false);
  }

  if (step.at === "password") {
    return (
      <form className="space-y-4" onSubmit={(e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const password = String(new FormData(e.currentTarget).get("password"));
        void run(async () => {
          const r = unwrap(await api.POST("/me/two-factor/setup", { body: { password } }));
          setStep({ at: "scan", secret: r.secret, uri: r.otpauth_uri });
        });
      }}>
        <div className="space-y-1.5">
          <Label htmlFor="tf-password">Your password</Label>
          <Input id="tf-password" name="password" type="password" required autoComplete="current-password" className="max-w-xs" />
        </div>
        <Problem>{error}</Problem>
        <Button type="submit" disabled={busy}>Continue</Button>
      </form>
    );
  }

  if (step.at === "scan") {
    return (
      <form className="space-y-4" onSubmit={(e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const code = String(new FormData(e.currentTarget).get("code"));
        void run(async () => {
          const r = unwrap(await api.POST("/me/two-factor/enable", { body: { code } }));
          setStep({ at: "codes", codes: r.recovery_codes });
          void qc.invalidateQueries({ queryKey: sessionQuery.queryKey });
          void qc.invalidateQueries({ queryKey: ["team"] });
        });
      }}>
        <div className="flex flex-wrap items-start gap-5">
          {/* a QR code is read as dark on light, so it keeps a white card in the dark theme too */}
          <div className="rounded-control border border-line bg-white p-3"><QRCodeSVG value={step.uri} size={148} marginSize={0} title="QR code for your authenticator app" /></div>
          <div className="min-w-0 flex-1 basis-56 space-y-3 text-sm">
            <p>Scan this with an authenticator app such as Google Authenticator, 1Password or Authy.</p>
            <div>
              <p className="text-xs text-ink-2">Can't scan? Type this key into the app instead:</p>
              <p className="mt-1 flex items-center gap-1"><code className="break-all text-xs">{groupSecret(step.secret)}</code>
                <Button type="button" size="icon" variant="ghost" aria-label="Copy the key" onClick={() => { void navigator.clipboard.writeText(step.secret); toast.success("Copied"); }}><Copy className="size-4" /></Button></p>
            </div>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tf-code">The 6-digit code the app shows</Label>
          <Input id="tf-code" name="code" required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} className="tnum max-w-[9rem] text-base tracking-widest" />
        </div>
        <Problem>{error}</Problem>
        <Button type="submit" disabled={busy}>Turn on two-factor</Button>
      </form>
    );
  }

  return <RecoveryCodes codes={step.codes} intro="Two-factor is on. Save these recovery codes now: they are shown this once."><Button onClick={onDone}>{doneLabel}</Button></RecoveryCodes>;
}

/** Ten one-time codes, shown once: copy or download, then confirm. */
export function RecoveryCodes({ codes, intro, children }: { codes: string[]; intro: string; children?: ReactNode }) {
  const text = `Spark recovery codes\nEach code signs you in once when you don't have your phone.\n\n${codes.join("\n")}\n`;
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "spark-recovery-codes.txt" });
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="space-y-4 text-sm">
      <p>{intro}</p>
      <ul aria-label="Recovery codes" className="tnum grid max-w-sm grid-cols-2 gap-x-6 gap-y-1.5 rounded-control border border-line bg-paper px-4 py-3 font-mono text-[13px]">
        {codes.map((c) => <li key={c}>{c}</li>)}
      </ul>
      <p className="text-xs text-ink-2">Each code signs you in once if you lose your phone. Keep them somewhere other than that phone, like a password manager.</p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => { void navigator.clipboard.writeText(codes.join("\n")); toast.success("Recovery codes copied"); }}><Copy className="size-4" />Copy</Button>
        <Button type="button" variant="outline" onClick={download}><Download className="size-4" />Download</Button>
        {children}
      </div>
    </div>
  );
}

export function Problem({ children }: { children: ReactNode }) {
  return children ? <p role="alert" className="text-sm text-st-failed">{children}</p> : null;
}
