/** Where people land when the workspace requires two-factor sign-in and they have not set it up. */
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { sessionQuery } from "@/app/session";
import { TwoFactorSetup } from "@/features/two-factor/setup";
import { api, unwrap } from "@/lib/api";
import { AuthFrame } from "@/pages/login";

export function TwoFactorPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const signOut = async () => {
    unwrap(await api.POST("/auth/logout"));
    await qc.invalidateQueries({ queryKey: sessionQuery.queryKey });
    void navigate({ to: "/login", search: {} });
  };
  return (
    <AuthFrame title="Set up two-factor sign-in">
      <div className="space-y-4">
        <p className="text-sm text-ink-2">This workspace asks everyone to sign in with a password and a code from an authenticator app. Setting it up takes about a minute.</p>
        <TwoFactorSetup doneLabel="Continue to Spark" onDone={() => window.location.assign(import.meta.env.BASE_URL)} />
        <p className="border-t border-line pt-3 text-sm"><button type="button" className="text-ink-2 underline-offset-4 hover:underline" onClick={() => void signOut()}>Sign out instead</button></p>
      </div>
    </AuthFrame>
  );
}
