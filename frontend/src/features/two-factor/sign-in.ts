/** What the sign-in form shows after the server refuses: which step to be on and what to say. */
export type SignInStep = "password" | "code";

export function afterSignInError(status: number, code: string, detail: string): { step?: SignInStep; error: string | null } {
  if (code === "two_factor_required") return { step: "code", error: null };
  if (code === "invalid_code") return { step: "code", error: "That code didn't work. Wait for the app to show a new one and try again." };
  if (code === "too_many_attempts") return { step: "code", error: detail };
  if (status === 429) return { error: "Too many tries. Wait a minute and try again." };
  if (status === 401) return { step: "password", error: "That email and password don't match." };
  return { error: "Could not sign in. Try again." };
}
