import Link from "next/link";
import { ArrowLeft, KeyRound, ShieldCheck, Sparkles } from "lucide-react";
import { LoginForm } from "@/components/iku/login-form";

function safeReturnTo(value: string | string[] | undefined): string {
  if (typeof value !== "string" || value.length > 2048 || !value.startsWith("/")) return "/";
  try {
    const target = new URL(value, "https://iku.invalid");
    if (target.origin !== "https://iku.invalid" || target.pathname !== "/api/auth/oidc/authorize" || !target.search) return "/";
    return `${target.pathname}${target.search}`;
  } catch {
    return "/";
  }
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ return_to?: string | string[] }> }) {
  const params = await searchParams;
  const continueTo = safeReturnTo(params.return_to);
  return (
    <main className="login-page">
      <Link href="/" className="login-back"><ArrowLeft size={16} /> Voltar ao início</Link>
      <section className="login-card">
        <span className="brand-mark login-mark"><Sparkles size={20} /></span>
        <span className="eyebrow muted-eyebrow">BEM-VINDO AO IKU</span>
        <h1>Entrar no teu espaço</h1>
        <div className="login-security"><ShieldCheck size={15} /> Sessão protegida por palavra-passe e 2FA de administrador.</div>
        <LoginForm continueTo={continueTo} />
        <p className="login-security"><KeyRound size={14} /> As credenciais são validadas pelo serviço local Iku Auth.</p>
      </section>
      <p className="login-footer">Iku · acesso privado aos teus serviços</p>
    </main>
  );
}
