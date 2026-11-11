"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Enrollment = { totp_secret: string; otpauth_uri: string; recovery_codes: string[] };

async function postAuth(path: string, body: Record<string, unknown>): Promise<{ response: Response; payload: Record<string, unknown> }> {
  const response = await fetch(`/api/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    cache: "no-store",
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
  return { response, payload };
}

export function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "bootstrap">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (mode === "login") {
        const { response, payload } = await postAuth("login", {
          email,
          password,
          client: "web",
          ...(mfaRequired ? { totp_code: totpCode } : {}),
        });
        if (!response.ok) {
          if (response.status === 428 && payload.detail === "mfa_required") {
            setMfaRequired(true);
            setMessage("Introduz o código de seis dígitos da tua app autenticadora.");
          } else if (response.status === 403 && payload.detail === "mfa_setup_required") {
            setError("O primeiro administrador ainda precisa de concluir a configuração de 2FA. Usa o setup inicial.");
          } else {
            setError("Não foi possível iniciar sessão. Confirma os dados e tenta novamente.");
          }
          return;
        }
        setPassword("");
        setTotpCode("");
        router.replace("/");
        router.refresh();
        return;
      }

      if (!enrollment) {
        const { response, payload } = await postAuth("bootstrap", { token: bootstrapToken, email, password });
        if (!response.ok) {
          setError(response.status === 409
            ? "O setup inicial já foi concluído. Entra com a tua conta."
            : "Não foi possível iniciar o setup. Confirma o token inicial e tenta novamente.");
          return;
        }
        setEnrollment({
          totp_secret: String(payload.totp_secret ?? ""),
          otpauth_uri: String(payload.otpauth_uri ?? ""),
          recovery_codes: Array.isArray(payload.recovery_codes) ? payload.recovery_codes.map(String) : [],
        });
        setMessage("Guarda o segredo e os códigos de recuperação num local seguro. Depois confirma um código TOTP.");
        return;
      }

      const { response } = await postAuth("bootstrap/verify-mfa", {
        token: bootstrapToken,
        email,
        code: totpCode,
      });
      if (!response.ok) {
        setError("O código não foi aceite. Aguarda o próximo código e tenta novamente.");
        return;
      }
      setPassword("");
      setBootstrapToken("");
      setTotpCode("");
      setEnrollment(null);
      setMode("login");
      setMfaRequired(true);
      setMessage("2FA configurado. Inicia sessão com a palavra-passe e um novo código TOTP.");
    } catch {
      setError("O serviço de autenticação não está disponível neste momento.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="login-intro">Sessão local segura para o portal Iku.</p>
      {error && <p className="auth-message auth-error" role="alert">{error}</p>}
      {message && <p className="auth-message auth-info" role="status">{message}</p>}

      <form onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="email">Email</label>
        <input id="email" className="text-input" type="email" autoComplete="username" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />

        {!enrollment && <>
          <label className="field-label" htmlFor="password">Palavra-passe</label>
          <input id="password" className="text-input" type="password" autoComplete={mode === "bootstrap" ? "new-password" : "current-password"} required minLength={mode === "bootstrap" ? 12 : 1} maxLength={1024} value={password} onChange={(event) => setPassword(event.target.value)} />
        </>}

        {mode === "bootstrap" && !enrollment && <>
          <label className="field-label" htmlFor="bootstrap-token">Token de setup inicial</label>
          <input id="bootstrap-token" className="text-input" type="password" autoComplete="off" required minLength={32} maxLength={512} value={bootstrapToken} onChange={(event) => setBootstrapToken(event.target.value)} />
        </>}

        {enrollment && <section className="mfa-enrollment" aria-label="Configuração de autenticação de dois fatores">
          <p><strong>Segredo TOTP</strong><code>{enrollment.totp_secret}</code></p>
          <p className="mfa-uri"><strong>Link de setup</strong><code>{enrollment.otpauth_uri}</code></p>
          <p><strong>Códigos de recuperação — guardar uma vez</strong></p>
          <code className="recovery-codes">{enrollment.recovery_codes.join("\n")}</code>
        </section>}

        {(mfaRequired || enrollment) && <>
          <label className="field-label" htmlFor="totp-code">Código de autenticação</label>
          <input id="totp-code" className="text-input" type="text" inputMode="numeric" autoComplete="one-time-code" required maxLength={16} value={totpCode} onChange={(event) => setTotpCode(event.target.value)} />
        </>}

        <button className="button button-primary login-submit" type="submit" disabled={busy}>
          {busy ? "A aguardar…" : mode === "bootstrap" ? (enrollment ? "Confirmar 2FA" : "Configurar administrador") : (mfaRequired ? "Confirmar e entrar" : "Entrar")}
        </button>
      </form>

      {!enrollment && <button className="auth-mode-toggle" type="button" onClick={() => {
        setMode(mode === "login" ? "bootstrap" : "login");
        setError("");
        setMessage("");
        setPassword("");
        setBootstrapToken("");
        setTotpCode("");
        setMfaRequired(false);
      }}>
        {mode === "login" ? "Configurar o primeiro administrador" : "Voltar ao login"}
      </button>}
    </>
  );
}
