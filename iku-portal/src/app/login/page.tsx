import Link from "next/link";
import { ArrowLeft, KeyRound, ShieldCheck, Sparkles } from "lucide-react";
import { LoginForm } from "@/components/iku/login-form";

export default function LoginPage() {
  return (
    <main className="login-page">
      <Link href="/" className="login-back"><ArrowLeft size={16} /> Voltar ao início</Link>
      <section className="login-card">
        <span className="brand-mark login-mark"><Sparkles size={20} /></span>
        <span className="eyebrow muted-eyebrow">BEM-VINDO AO IKU</span>
        <h1>Entrar no teu espaço</h1>
        <div className="login-security"><ShieldCheck size={15} /> Sessão protegida por palavra-passe e 2FA de administrador.</div>
        <LoginForm />
        <p className="login-security"><KeyRound size={14} /> As credenciais são validadas pelo serviço local Iku Auth.</p>
      </section>
      <p className="login-footer">Iku · acesso privado aos teus serviços</p>
    </main>
  );
}
