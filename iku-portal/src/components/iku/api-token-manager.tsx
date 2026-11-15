"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Check, Copy, KeyRound, Plus, RotateCcw, Trash2 } from "lucide-react";
import styles from "./api-token-manager.module.css";

type ApiToken = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  expired: boolean;
};

const availableScopes = [
  { id: "profile:read", label: "Ler perfil" },
  { id: "sessions:read", label: "Ler sessões" },
  { id: "sessions:revoke", label: "Terminar sessões" },
];

function dateLabel(value: string | null): string {
  if (!value) return "Nunca usado";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "indisponível" : date.toLocaleString();
}

export function ApiTokenManager() {
  const router = useRouter();
  const [tokens, setTokens] = useState<ApiToken[] | null>(null);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["profile:read"]);
  const [expiresInDays, setExpiresInDays] = useState(90);
  const [createdToken, setCreatedToken] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/auth/api-tokens", { credentials: "same-origin", cache: "no-store" });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("Não foi possível carregar os tokens.");
      const payload = await response.json() as { tokens?: ApiToken[] };
      setTokens(Array.isArray(payload.tokens) ? payload.tokens : []);
    } catch {
      setTokens([]);
      setError("Não foi possível carregar os tokens. Tenta novamente.");
    }
  }, [router]);

  useEffect(() => { void reload(); }, [reload]);

  function toggleScope(scope: string) {
    setScopes((current) => current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope]);
  }

  async function createToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    setCreatedToken("");
    setCopied(false);
    try {
      const response = await fetch("/api/auth/api-tokens", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, scopes, expires_in_days: expiresInDays }),
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      const payload = await response.json() as { token?: string; detail?: string };
      if (!response.ok || !payload.token) throw new Error("Não foi possível criar o token. Confirma o nome e os acessos escolhidos.");
      setCreatedToken(payload.token);
      setNotice("Copia este token agora. O valor completo só é apresentado uma vez.");
      setName("");
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível criar o token.");
    } finally {
      setBusy(false);
    }
  }

  async function copyToken() {
    try {
      await navigator.clipboard.writeText(createdToken);
      setCopied(true);
    } catch {
      setError("Não foi possível copiar automaticamente. Seleciona e copia o valor apresentado.");
    }
  }

  async function revokeToken(token: ApiToken) {
    if (!window.confirm(`Revogar o token “${token.name}”? Os sistemas que o usam deixam de ter acesso.`)) return;
    setBusyId(token.id);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/auth/api-tokens/revoke", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_id: token.id }),
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("Não foi possível revogar o token.");
      if (createdToken.startsWith(token.prefix)) setCreatedToken("");
      setNotice(`Token “${token.name}” revogado.`);
      await reload();
    } catch {
      setError("Não foi possível revogar o token. Atualiza a lista e tenta novamente.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className={styles.manager} aria-labelledby="api-token-heading">
      <div className="page-heading"><div><span className="eyebrow muted-eyebrow">ACESSO DE APLICAÇÕES</span><h2 id="api-token-heading">Tokens de API</h2><p>Cria credenciais por aplicação, com acessos limitados e validade máxima de um ano.</p></div></div>
      {error && <p className="auth-message auth-error" role="alert">{error}</p>}
      {notice && <p className="auth-message auth-info" role="status">{notice}</p>}

      {createdToken && <div className={styles.secret}>
        <label htmlFor="new-api-token">Token apresentado uma vez</label>
        <div className={styles.secretRow}><input id="new-api-token" readOnly value={createdToken} autoComplete="off" /><button className="button button-quiet" type="button" onClick={() => void copyToken()}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copiado" : "Copiar"}</button></div>
        <p>Guarda-o no gestor de segredos da aplicação. A Iku guarda apenas o hash.</p>
        <button className="button button-quiet" type="button" onClick={() => { setCreatedToken(""); setNotice(""); }}>Fechar valor</button>
      </div>}

      <form className={styles.form} onSubmit={(event) => void createToken(event)}>
        <label className={styles.field}>Nome da aplicação<input value={name} onChange={(event) => setName(event.target.value)} maxLength={80} minLength={1} required placeholder="Ex.: integração de backup" autoComplete="off" /></label>
        <fieldset className={styles.scopes}>
          <legend>Acessos autorizados</legend>
          {availableScopes.map((scope) => <label key={scope.id}><input type="checkbox" checked={scopes.includes(scope.id)} onChange={() => toggleScope(scope.id)} />{scope.label}<code>{scope.id}</code></label>)}
        </fieldset>
        <label className={styles.field}>Expira em<select value={expiresInDays} onChange={(event) => setExpiresInDays(Number(event.target.value))}><option value={30}>30 dias</option><option value={90}>90 dias</option><option value={180}>180 dias</option><option value={365}>1 ano</option></select></label>
        <button className="button button-primary" type="submit" disabled={busy || !name.trim() || scopes.length === 0}><Plus size={15} />{busy ? "A criar…" : "Criar token"}</button>
      </form>

      <div className={styles.toolbar}><h3>Tokens ativos</h3><button className="button button-quiet" type="button" onClick={() => void reload()}><RotateCcw size={14} />Atualizar</button></div>
      {tokens === null ? <p role="status">A carregar tokens…</p> : tokens.length === 0 && !error ? <section className="empty-panel"><div className="empty-copy"><h3>Ainda não há tokens de API</h3><p>Cria um token apenas quando uma aplicação precisar de aceder à API da Iku.</p></div></section> : (
        <div className={styles.list}>
          {tokens.map((token) => <article className={`service-card ${styles.card}`} key={token.id}>
            <div className="service-card-head"><span className="service-icon"><KeyRound size={19} /></span><span className={`status-tag ${token.expired ? "offline" : "online"}`}>{token.expired ? "Expirado" : "Ativo"}</span></div>
            <h3>{token.name}</h3>
            <p className={styles.prefix}><code>{token.prefix}••••••••</code></p>
            <p className={styles.meta}>Acessos: {token.scopes.join(", ")}</p>
            <p className={styles.meta}>Criado: {dateLabel(token.created_at)} · Expira: {token.expires_at ? dateLabel(token.expires_at) : "Nunca"}</p>
            <p className={styles.meta}>Último uso: {dateLabel(token.last_used_at)}</p>
            <button className={`button button-quiet ${styles.revoke}`} type="button" disabled={busyId === token.id} onClick={() => void revokeToken(token)}><Trash2 size={14} />{busyId === token.id ? "A revogar…" : "Revogar"}</button>
          </article>)}
        </div>
      )}
    </section>
  );
}
