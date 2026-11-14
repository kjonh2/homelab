"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Check, Copy, Link2, RefreshCw, UserPlus, UserRoundX, UserRoundCheck, X } from "lucide-react";
import styles from "./admin-user-manager.module.css";

type AdminUser = {
  id: string;
  email: string;
  disabled: boolean;
  roles: string[];
  mfa_enabled: boolean;
  created_at: string;
  updated_at: string;
};

type AdminInvite = {
  id: string;
  email: string;
  roles: string[];
  created_at: string;
  expires_at: string;
};

type OidcSubjectMapping = { user_id: string; subject: string };

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "indisponível" : date.toLocaleString();
}

export function AdminUserManager({ currentUserId }: Readonly<{ currentUserId: string }>) {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [invites, setInvites] = useState<AdminInvite[]>([]);
  const [oidcSubjects, setOidcSubjects] = useState<Record<string, string>>({});
  const [oidcSubjectDrafts, setOidcSubjectDrafts] = useState<Record<string, string>>({});
  const [email, setEmail] = useState("");
  const [inviteToken, setInviteToken] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    setError("");
    try {
      const [response, mappingResponse] = await Promise.all([
        fetch("/api/auth/admin/users", { credentials: "same-origin", cache: "no-store" }),
        fetch("/api/auth/admin/oidc-subjects", { credentials: "same-origin", cache: "no-store" }),
      ]);
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (response.status === 403) throw new Error("Esta conta não tem permissões de administração.");
      if (!response.ok || !mappingResponse.ok) throw new Error("Não foi possível carregar as contas e os vínculos de acesso.");
      const payload = await response.json() as { users?: AdminUser[]; invites?: AdminInvite[] };
      const mappingPayload = await mappingResponse.json() as { mappings?: OidcSubjectMapping[] };
      const mappings = Object.fromEntries((mappingPayload.mappings ?? []).map((mapping) => [mapping.user_id, mapping.subject]));
      setUsers(Array.isArray(payload.users) ? payload.users : []);
      setInvites(Array.isArray(payload.invites) ? payload.invites : []);
      setOidcSubjects(mappings);
      setOidcSubjectDrafts(mappings);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível carregar as contas.");
      setUsers([]);
    }
  }, [router]);

  useEffect(() => { void reload(); }, [reload]);

  async function createInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    setInviteToken("");
    setCopied(false);
    try {
      const response = await fetch("/api/auth/admin/invites", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }),
      });
      if (response.status === 401) { router.replace("/login"); return; }
      const payload = await response.json() as { invitation_token?: string; detail?: string };
      if (response.status === 409) throw new Error("Já existe uma conta para este email.");
      if (!response.ok || !payload.invitation_token) throw new Error("Não foi possível criar o convite. Confirma o endereço de email.");
      setInviteToken(payload.invitation_token);
      setEmail("");
      setNotice("Copia o convite e envia-o por um canal privado. O código só é mostrado uma vez e expira em 72 horas.");
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível criar o convite.");
    } finally {
      setBusy(false);
    }
  }

  async function copyInvite() {
    try {
      await navigator.clipboard.writeText(inviteToken);
      setCopied(true);
    } catch {
      setError("A cópia automática falhou. Seleciona e copia o código apresentado.");
    }
  }

  async function setDisabled(user: AdminUser) {
    const action = user.disabled ? "reativar" : "desativar";
    if (!window.confirm(`Queres ${action} a conta de ${user.email}?${user.disabled ? "" : " As sessões e tokens existentes serão revogados."}`)) return;
    setBusyId(user.id);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/auth/admin/users/status", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.id, disabled: !user.disabled }),
      });
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) throw new Error("Não foi possível alterar o estado desta conta.");
      setNotice(user.disabled ? `A conta ${user.email} foi reativada.` : `A conta ${user.email} foi desativada e os acessos foram revogados.`);
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível alterar esta conta.");
    } finally {
      setBusyId("");
    }
  }

  async function revokeInvite(invite: AdminInvite) {
    if (!window.confirm(`Cancelar o convite enviado a ${invite.email}?`)) return;
    setBusyId(invite.id);
    setError("");
    try {
      const response = await fetch("/api/auth/admin/invites/revoke", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ invite_id: invite.id }),
      });
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) throw new Error("Não foi possível cancelar o convite.");
      setNotice(`Convite de ${invite.email} cancelado.`);
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível cancelar o convite.");
    } finally {
      setBusyId("");
    }
  }

  async function saveOidcSubject(user: AdminUser) {
    const subject = (oidcSubjectDrafts[user.id] ?? "").trim();
    const existing = oidcSubjects[user.id];
    if (subject && subject === existing) return;
    if (subject && !window.confirm(`Ligar ${user.email} à conta Nextcloud “${subject}”? O UID tem de ser exatamente o da conta existente; isso determina quais ficheiros ficam acessíveis.`)) return;
    if (!subject && existing && !window.confirm(`Remover o vínculo Nextcloud de ${user.email}? O próximo login usará o ID interno Iku.`)) return;
    setBusyId(user.id);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/auth/admin/oidc-subjects${subject ? "" : "/clear"}`, {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(subject ? { user_id: user.id, subject } : { user_id: user.id }),
      });
      if (response.status === 401) { router.replace("/login"); return; }
      if (response.status === 409) throw new Error("Esse UID do Nextcloud já está ligado a outra conta Iku.");
      if (response.status === 422) throw new Error("O UID do Nextcloud tem caracteres ou comprimento inválidos.");
      if (!response.ok) throw new Error("Não foi possível guardar o vínculo OIDC.");
      setNotice(subject ? `A conta Iku ficou ligada ao UID Nextcloud “${subject}”.` : `O vínculo Nextcloud de ${user.email} foi removido.`);
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível guardar o vínculo OIDC.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className={styles.manager} aria-labelledby="admin-users-heading">
      <div className="page-heading"><div><span className="eyebrow muted-eyebrow">ACESSO RESTRITO · ADMIN</span><h2 id="admin-users-heading">Contas Iku</h2><p>Convida pessoas sem registo público e revoga acessos quando necessário.</p></div></div>
      {error && <p className="auth-message auth-error" role="alert">{error}</p>}
      {notice && <p className="auth-message auth-info" role="status">{notice}</p>}

      {inviteToken && <div className={styles.inviteSecret}>
        <h3>Código de convite</h3>
        <p>Envia este código à pessoa por um canal privado. Ela deve introduzi-lo em <strong>/invite</strong>; não inclui o código num link ou mensagem pública.</p>
        <div className={styles.tokenRow}><input aria-label="Código de convite" readOnly value={inviteToken} autoComplete="off" /><button className="button button-quiet" type="button" onClick={() => void copyInvite()}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copiado" : "Copiar"}</button></div>
        <button className="button button-quiet" type="button" onClick={() => setInviteToken("")}><X size={14} />Fechar código</button>
      </div>}

      <form className={styles.panel} onSubmit={(event) => void createInvite(event)}>
        <h3><UserPlus size={16} /> Convidar pessoa</h3>
        <p>O convite só permite criar uma conta normal, expira em 72 horas e pode ser usado uma vez.</p>
        <label className={styles.field}>Email da pessoa<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required autoComplete="email" placeholder="nome@exemplo.pt" /></label>
        <button className="button button-primary" type="submit" disabled={busy || !email.trim()}><UserPlus size={15} />{busy ? "A criar convite…" : "Criar convite"}</button>
      </form>

      <div className={styles.toolbar}><h2>Utilizadores</h2><button className="button button-quiet" type="button" onClick={() => void reload()}><RefreshCw size={14} />Atualizar</button></div>
      {users === null ? <p role="status">A carregar contas…</p> : users.length === 0 ? <section className="empty-panel"><div className="empty-copy"><h3>Não há contas para apresentar</h3></div></section> : (
        <div className={styles.list}>
          {users.map((user) => <article className={styles.row} key={user.id}>
            <div className={styles.identity}>
              <strong>{user.email}{user.id === currentUserId ? " · tu" : ""}</strong>
              <span className={styles.meta}>Funções: {user.roles.join(", ") || "sem função"} · 2FA: {user.mfa_enabled ? "ativo" : "não ativo"}</span>
              <span className={styles.meta}>Criada: {dateLabel(user.created_at)} · Estado: {user.disabled ? "desativada" : "ativa"}</span>
            </div>
            <div className={styles.actions}>
              <span className={`status-tag ${user.disabled ? "offline" : "online"}`}>{user.disabled ? "Desativada" : "Ativa"}</span>
              {user.id !== currentUserId && <button className="button button-quiet" type="button" disabled={busyId === user.id} onClick={() => void setDisabled(user)}>{user.disabled ? <UserRoundCheck size={14} /> : <UserRoundX size={14} />}{busyId === user.id ? "A guardar…" : user.disabled ? "Reativar" : "Desativar"}</button>}
            </div>
            <div className={styles.oidcLink}>
              <label className={styles.field}>UID da conta Nextcloud
                <input
                  type="text" maxLength={255} autoComplete="off" placeholder="Ex.: ikuadmin"
                  aria-label={`UID Nextcloud para ${user.email}`}
                  value={oidcSubjectDrafts[user.id] ?? ""}
                  onChange={(event) => setOidcSubjectDrafts((current) => ({ ...current, [user.id]: event.target.value }))}
                  disabled={Boolean(user.disabled) || busyId === user.id}
                />
              </label>
              <button className="button button-quiet" type="button" disabled={Boolean(user.disabled) || busyId === user.id || (oidcSubjectDrafts[user.id] ?? "").trim() === (oidcSubjects[user.id] ?? "") || (!(oidcSubjectDrafts[user.id] ?? "").trim() && !oidcSubjects[user.id])} onClick={() => void saveOidcSubject(user)}><Link2 size={14} />{busyId === user.id ? "A guardar…" : !(oidcSubjectDrafts[user.id] ?? "").trim() && oidcSubjects[user.id] ? "Remover vínculo" : oidcSubjects[user.id] ? "Guardar vínculo" : "Ligar conta"}</button>
            </div>
          </article>)}
        </div>
      )}

      <div className={styles.toolbar}><h2>Convites pendentes</h2></div>
      {invites.length === 0 ? <section className="empty-panel"><div className="empty-copy"><p>Não há convites pendentes.</p></div></section> : (
        <div className={styles.list}>
          {invites.map((invite) => <article className={styles.row} key={invite.id}>
            <div className={styles.identity}><strong>{invite.email}</strong><span className={styles.meta}>Expira: {dateLabel(invite.expires_at)} · Funções: {invite.roles.join(", ")}</span></div>
            <div className={styles.actions}><button className="button button-quiet" type="button" disabled={busyId === invite.id} onClick={() => void revokeInvite(invite)}><X size={14} />{busyId === invite.id ? "A cancelar…" : "Cancelar convite"}</button></div>
          </article>)}
        </div>
      )}
    </section>
  );
}
