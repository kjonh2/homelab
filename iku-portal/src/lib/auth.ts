import { cookies } from "next/headers";

export type AuthSession = { user: { id: string; email: string; roles: string[]; mfa_enabled?: boolean } };

export async function getAuthSession(): Promise<AuthSession | null> {
  const token = (await cookies()).get("iku_session")?.value;
  if (!token) return null;
  const base = (process.env.IKU_AUTH_URL ?? "http://iku-auth.iku.svc.cluster.local:8080").replace(/\/$/, "");
  const response = await fetch(`${base}/v1/auth/session`, {
    headers: { Cookie: `iku_session=${token}` },
    cache: "no-store",
    signal: AbortSignal.timeout(4_000),
  });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("auth service unavailable");
  return await response.json() as AuthSession;
}
