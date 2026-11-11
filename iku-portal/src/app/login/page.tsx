import Link from "next/link";
import { ArrowLeft, KeyRound, ShieldCheck, Sparkles } from "lucide-react";

export default function LoginPage() {
  return (
    <main className="login-page"><Link href="/" className="login-back"><ArrowLeft size={16} /> Voltar ao início</Link><section className="login-card"><span className="brand-mark login-mark"><Sparkles size={20} /></span><span className="eyebrow muted-eyebrow">BEM-VINDO AO IKU</span><h1>Entrar no teu espaço</h1><p className="login-intro">Uma sessão segura para os teus serviços e dispositivos.</p><div className="login-disabled"><span className="login-disabled-icon"><KeyRound size={19} /></span><div><strong>Autenticação ainda não ligada</strong><p>O serviço local de login, sessões e 2FA ainda não está instalado. O formulário permanece inativo até essa ligação existir.</p></div></div><label className="field-label" htmlFor="email">Email</label><input id="email" className="text-input" type="email" autoComplete="username" placeholder="nome@exemplo.pt" disabled /><label className="field-label" htmlFor="password">Palavra-passe</label><input id="password" className="text-input" type="password" autoComplete="current-password" placeholder="••••••••••••" disabled /><button className="button button-primary login-submit" disabled>Login indisponível</button><div className="login-security"><ShieldCheck size={15} /> A autenticação nunca será simulada nesta pré-visualização.</div></section><p className="login-footer">Iku · acesso privado aos teus serviços</p></main>
  );
}
