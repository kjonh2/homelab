"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, LaptopMinimal, Smartphone, X } from "lucide-react";
import styles from "./session-manager.module.css";

type UserSession = {
  id: string;
  client: string;
  device_name: string;
  created_at: string;
  expires_at: string;
  last_seen_at: string;
  current: boolean;
};

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "indisponível" : date.toLocaleString();
}

export function SessionManager() {
  const router = useRouter();
  const [sessions, setSessions] = useState<UserSession[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/auth/sessions", { credentials: "same-origin", cache: "no-store" });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("Não foi possível carregar as sessões.");
      const payload = await response.json() as { sessions?: UserSession[] };
      setSessions(Array.isArray(payload.sessions) ? payload.sessions : []);
    } catch {
      setError("Não foi possível carregar as sessões. Tenta novamente.");
      setSessions([]);
    }
  }, [router]);

  useEffect(() => { void reload(); }, [reload]);

  async function revoke(session: UserSession) {
    const label = session.current ? "esta sessão" : `a sessão ${session.device_name || session.client}`;
    if (!window.confirm(`Queres terminar ${label}?`)) return;
    setBusyId(session.id);
    setError("");
    try {
      const response = await fetch("/api/auth/sessions/revoke", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: session.id }),
      });
      if (!response.ok) throw new Error("A sessão não foi revogada.");
      const result = await response.json() as { current?: boolean };
      if (result.current) {
        router.replace("/login");
        router.refresh();
        return;
      }
      await reload();
    } catch {
      setError("Não foi possível terminar a sessão. Atualiza a lista e tenta de novo.");
    } finally {
      setBusyId(null);
    }
  }

  if (sessions === null) return <p role="status">A carregar sessões…</p>;

  return (
    <div className={styles.manager} aria-live="polite">
      <div className={styles.toolbar}>
        <p>Estas sessões pertencem à tua conta. Revogar uma sessão Android também invalida o respetivo token de atualização.</p>
        <button className="button button-quiet" type="button" onClick={() => void reload()}><Activity size={15} /> Atualizar</button>
      </div>
      {error && <p className="auth-message auth-error" role="alert">{error}</p>}
      {sessions.length === 0 && !error ? <section className="empty-panel"><div className="empty-copy"><h2>Não há sessões ativas</h2><p>Inicia sessão novamente para continuar.</p></div></section> : sessions.length > 0 ? (
        <div className={styles.list}>
          {sessions.map((session) => {
            const Icon = session.client === "android" ? Smartphone : LaptopMinimal;
            return <article className={`service-card ${styles.card}`} key={session.id}>
              <div className="service-card-head"><span className="service-icon"><Icon size={20} /></span><span className={`status-tag ${session.current ? "online" : ""}`}>{session.current ? "Sessão atual" : session.client}</span></div>
              <h2>{session.device_name || (session.client === "android" ? "Android" : "Navegador")}</h2>
              <p className={styles.meta}>Iniciada: {dateLabel(session.created_at)}</p>
              <p className={styles.meta}>Última atividade: {dateLabel(session.last_seen_at)}</p>
              <p className={styles.meta}>Expira: {dateLabel(session.expires_at)}</p>
              <button className={`button button-quiet ${styles.revoke}`} type="button" disabled={busyId === session.id} onClick={() => void revoke(session)}>
                <X size={15} /> {busyId === session.id ? "A terminar…" : session.current ? "Terminar esta sessão" : "Revogar sessão"}
              </button>
            </article>;
          })}
        </div>
      ) : null}
    </div>
  );
}
