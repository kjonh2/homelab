"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity, ArrowUpRight, Bell, Boxes, ChevronRight, CircleHelp, Cloud, Download,
  FileClock, House, LayoutDashboard, LockKeyhole, Menu, MonitorSmartphone,
  Settings2, ShieldCheck, Sparkles, UserRound, X,
} from "lucide-react";
import { portalSections } from "@/lib/portal-sections";

const icons = {
  layout: LayoutDashboard,
  user: UserRound,
  devices: MonitorSmartphone,
  settings: Settings2,
  download: Download,
  release: FileClock,
  services: Boxes,
  sessions: Activity,
  security: ShieldCheck,
  admin: LockKeyhole,
} as const;

type PortalUser = { email: string; roles: string[] };

function NavItems({ close, isAdmin }: { close?: () => void; isAdmin: boolean }) {
  const pathname = usePathname();
  return (
    <>
      <Link className={`nav-link ${pathname === "/" ? "active" : ""}`} href="/" onClick={close}>
        <House size={18} strokeWidth={1.8} /><span>Início</span>
      </Link>
      {portalSections.filter((section) => section.slug !== "admin" || isAdmin).map((section) => {
        const Icon = icons[section.icon as keyof typeof icons];
        const active = pathname === `/${section.slug}`;
        return (
          <Link key={section.slug} className={`nav-link ${active ? "active" : ""}`} href={`/${section.slug}`} onClick={close}>
            <Icon size={18} strokeWidth={1.8} /><span>{section.label}</span>
            {section.slug === "admin" && <span className="nav-lock" aria-label="Acesso restrito"><LockKeyhole size={13} /></span>}
          </Link>
        );
      })}
    </>
  );
}

export function PortalShell({ children, user }: Readonly<{ children: React.ReactNode; user: PortalUser | null }>) {
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();
  const current = portalSections.find((section) => pathname === `/${section.slug}`);
  const isAdmin = Boolean(user?.roles.includes("admin"));
  const avatar = user?.email?.slice(0, 1).toLocaleUpperCase() ?? "I";

  return (
    <div className="portal-frame">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Iku, início">
          <span className="brand-mark"><Sparkles size={19} /></span>
          <span className="brand-copy"><strong>iku</strong><small>O TEU ESPAÇO</small></span>
        </Link>
        <div className="sidebar-label">ESPAÇO PESSOAL</div>
        <nav className="main-nav" aria-label="Navegação principal"><NavItems isAdmin={isAdmin} /></nav>
        <div className="sidebar-bottom">
          <div className="privacy-note"><ShieldCheck size={16} /><span>Privado por desenho</span></div>
          <div className="sidebar-profile"><span className="avatar">{avatar}</span><span><strong>{user?.email ?? "Pré-visualização"}</strong><small>{isAdmin ? "Administrador Iku" : "Conta Iku"}</small></span></div>
        </div>
      </aside>

      {menuOpen && <button className="mobile-scrim" aria-label="Fechar menu" onClick={() => setMenuOpen(false)} />}
      <aside className={`mobile-drawer ${menuOpen ? "open" : ""}`} aria-hidden={!menuOpen}>
        <div className="drawer-head"><span className="brand-mark"><Sparkles size={19} /></span><strong>iku</strong><button className="icon-button" aria-label="Fechar menu" onClick={() => setMenuOpen(false)}><X size={19} /></button></div>
        <nav className="main-nav" aria-label="Navegação móvel"><NavItems close={() => setMenuOpen(false)} isAdmin={isAdmin} /></nav>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu-button" aria-label="Abrir menu" onClick={() => setMenuOpen(true)}><Menu size={20} /></button>
            <div className="breadcrumb"><span>Iku</span><ChevronRight size={15} /><strong>{current?.label ?? "Início"}</strong></div>
          </div>
          <div className="topbar-actions">
            <span className="preview-pill"><span className="status-dot" /> {user ? "Sessão ativa" : "Pré-visualização"}</span>
            <button className="icon-button help-button" aria-label="Ajuda"><CircleHelp size={19} /></button>
            <button className="icon-button" aria-label="Notificações"><Bell size={19} /><span className="notification-dot" /></button>
            <span className="avatar avatar-small">{avatar}</span>
          </div>
        </header>
        <div className="page-content">{children}</div>
        <footer className="site-footer"><span>iku · o teu espaço digital</span><span><LockKeyhole size={13} /> {user ? "Sessão local Iku" : "Pré-visualização privada"}</span></footer>
      </main>
    </div>
  );
}

export function PreviewNotice() {
  return <div className="preview-notice"><Cloud size={17} /><span>O estado dos serviços é consultado ao vivo. Algumas áreas de gestão ainda estão a ser ligadas.</span></div>;
}
