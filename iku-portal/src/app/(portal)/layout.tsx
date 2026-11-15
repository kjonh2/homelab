import { PortalShell } from "@/components/iku/portal-shell";
import { redirect } from "next/navigation";
import { getAuthSession, type AuthSession } from "@/lib/auth";

export default async function PortalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  let user: AuthSession["user"] | null = null;
  if (process.env.IKU_AUTH_ENFORCE === "true") {
    let session: AuthSession | null;
    try {
      session = await getAuthSession();
    } catch {
      return <main className="auth-unavailable"><section><h1>Iku Auth indisponível</h1><p>O portal manteve o acesso fechado porque não conseguiu validar a sessão. Tenta novamente mais tarde.</p></section></main>;
    }
    if (!session) redirect("/login");
    user = session.user;
  }
  return <PortalShell user={user}>{children}</PortalShell>;
}
