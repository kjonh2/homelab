"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft, Check, KeyRound, UserPlus } from "lucide-react";

export function InviteAcceptForm() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(false);
  const [error, setError] = useState("");

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmation) {
      setError("As palavras-passe não coincidem.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/auth/invites/accept", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token.trim(), password }),
      });
      const payload = await response.json() as { status?: string };
      if (!response.ok || payload.status !== "account_created") {
        throw new Error(response.status === 409 ? "Já existe uma conta com este email." : "O convite é inválido, expirou ou já foi usado.");
      }
      setToken("");
      setPassword("");
      setConfirmation("");
      setCreated(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível ativar a conta.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <Link className="login-back" href="/login"><ArrowLeft size={15} />Voltar ao login</Link>
      <section className="login-card" aria-labelledby="invite-title">
        <Link className="brand login-mark" href="/" aria-label="Iku, início"><span className="brand-mark"><UserPlus size={19} /></span><span className="brand-copy"><strong>iku</strong><small>CONVITE DE CONTA</small></span></Link>
        <span className="eyebrow">ATIVAÇÃO PRIVADA</span>
        <h1 id="invite-title">Criar conta Iku</h1>
        {created ? <>
          <p className="login-intro">A conta foi criada. Já podes iniciar sessão com o email convidado e a palavra-passe que escolheste.</p>
          <Link className="button button-primary login-submit" href="/login"><Check size={16} />Ir para o login</Link>
        </> : <>
          <p className="login-intro">Introduz o código recebido pelo administrador. O convite é de uso único e expira em 72 horas.</p>
          {error && <p className="auth-message auth-error" role="alert">{error}</p>}
          <form onSubmit={(event) => void accept(event)}>
            <label className="field-label" htmlFor="invite-token">Código de convite</label>
            <input className="text-input" id="invite-token" value={token} onChange={(event) => setToken(event.target.value)} minLength={32} maxLength={512} required autoComplete="off" spellCheck={false} />
            <label className="field-label" htmlFor="invite-password">Palavra-passe</label>
            <input className="text-input" id="invite-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={1024} required autoComplete="new-password" />
            <label className="field-label" htmlFor="invite-password-confirm">Confirmar palavra-passe</label>
            <input className="text-input" id="invite-password-confirm" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} maxLength={1024} required autoComplete="new-password" />
            <button className="button button-primary login-submit" type="submit" disabled={busy || token.trim().length < 32 || password.length < 12 || confirmation.length < 12}><KeyRound size={15} />{busy ? "A criar conta…" : "Ativar conta"}</button>
          </form>
        </>}
        <p className="login-security"><KeyRound size={13} />O código é enviado no corpo HTTPS e nunca aparece no endereço.</p>
      </section>
    </main>
  );
}
