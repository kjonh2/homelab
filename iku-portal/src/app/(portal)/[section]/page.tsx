import { notFound } from "next/navigation";
import { ArrowRight, LockKeyhole, ShieldCheck, UserRound, Download, FileClock, Settings2, KeyRound } from "lucide-react";
import { PreviewNotice } from "@/components/iku/portal-shell";
import { ServiceCards } from "@/components/iku/service-cards";
import { sectionBySlug } from "@/lib/portal-sections";
import { getServiceStatus } from "@/lib/services";
import { getAuthSession } from "@/lib/auth";
import { redirect } from "next/navigation";
import { SessionManager } from "@/components/iku/session-manager";

export const dynamic = "force-dynamic";

export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section: slug } = await params;
  const section = sectionBySlug[slug];
  if (!section) notFound();

  if (slug === "admin" && process.env.IKU_AUTH_ENFORCE === "true") {
    const session = await getAuthSession();
    if (!session) redirect("/login");
    if (!session.user.roles.includes("admin")) notFound();
  }

  if (slug === "services") {
    const services = await getServiceStatus();
    const online = services.filter((service) => service.state === "online").length;
    return (
      <div className="section-page">
        <PreviewNotice />
        <div className="page-heading"><div><span className="eyebrow muted-eyebrow">VPS · ESTADO AO VIVO</span><h1>Serviços</h1><p>{online} de {services.length} serviços respondem pela rede do cluster.</p></div></div>
        <ServiceCards services={services} />
        <div className="setup-card"><div><span className="eyebrow muted-eyebrow">ACESSO</span><h3>Os atalhos são privados</h3><p>Abre o serviço com um dispositivo ligado ao tailnet Tailscale e autorizado nesta rede.</p></div></div>
      </div>
    );
  }

  const admin = slug === "admin";
  let session = null;
  if (["profile", "devices", "sessions", "security", "settings", "admin"].includes(slug)) {
    try { session = await getAuthSession(); } catch { session = null; }
    if (process.env.IKU_AUTH_ENFORCE === "true" && !session) redirect("/login");
  }

  if (slug === "devices") {
    return <div className="section-page"><PreviewNotice /><div className="page-heading"><div><span className="eyebrow muted-eyebrow">ACESSO À CONTA</span><h1>Dispositivos</h1><p>Consulta os dispositivos ligados à tua conta e termina acessos que já não reconheces.</p></div></div><SessionManager /></div>;
  }

  if (slug === "sessions") {
    return <div className="section-page"><PreviewNotice /><div className="page-heading"><div><span className="eyebrow muted-eyebrow">SESSÕES ATIVAS</span><h1>Sessões</h1><p>Consulta e termina os dispositivos com acesso à tua conta Iku.</p></div></div><SessionManager /></div>;
  }

  if (slug === "profile" || slug === "security") {
    const current = session?.session;
    const user = session?.user;
    const details = {
      profile: { eyebrow: "CONTA IKU", title: "Perfil", icon: UserRound, heading: user?.email ?? "Conta não disponível", body: `Função: ${user?.roles.join(", ") || "conta"}. O portal usa autenticação local Iku.`, meta: `ID de utilizador: ${user?.id ?? "indisponível"}` },
      security: { eyebrow: "PROTEÇÃO DA CONTA", title: "Segurança", icon: ShieldCheck, heading: user?.mfa_enabled ? "2FA ativo" : "2FA não ativo", body: "O login do portal usa sessão Iku protegida por cookie. O primeiro administrador requer 2FA; a gestão de fatores e tokens ainda não está disponível nesta página.", meta: "Acesso às páginas privadas limitado ao tailnet Tailscale." },
    }[slug];
    const Icon = details.icon;
    return <div className="section-page"><PreviewNotice /><div className="page-heading"><div><span className="eyebrow muted-eyebrow">{details.eyebrow}</span><h1>{details.title}</h1><p>Informação fornecida pela sessão autenticada atual.</p></div></div><section className="empty-panel"><div className="empty-icon"><Icon size={22} /></div><div className="empty-copy"><h2>{details.heading}</h2><p>{details.body}</p><span className="pending-line"><KeyRound size={13} /> {details.meta}</span></div></section></div>;
  }

  const comingSoon = slug === "settings" || slug === "downloads" || slug === "releases";
  const pageIcon = slug === "settings" ? Settings2 : slug === "downloads" ? Download : slug === "releases" ? FileClock : LockKeyhole;
  const PageIcon = pageIcon;
  return (
    <div className="section-page">
      <PreviewNotice />
      <div className="page-heading"><div><span className="eyebrow muted-eyebrow">{admin ? "ACESSO RESTRITO" : "ESPAÇO PESSOAL"}</span><h1>{section.label}</h1><p>{section.description}</p></div>{admin && <span className="status-tag pending"><LockKeyhole size={13} /> Requer autenticação</span>}</div>
      <section className="empty-panel"><div className="empty-icon"><PageIcon size={22} /></div><div className="empty-copy"><h2>{admin ? "Área de administração protegida" : comingSoon ? "Esta área ainda não está disponível" : "Dados desta secção ainda não disponíveis"}</h2><p>{admin ? "O acesso exige uma sessão válida e a função de administrador. Os controlos administrativos ainda não têm API implementada." : comingSoon ? "A sessão e o backend Iku estão ativos, mas ainda não existe armazenamento ou API para esta funcionalidade." : "A sessão Iku está ativa. Esta secção ainda não tem dados ligados a um serviço."}</p><span className="pending-line"><span className="status-dot" /> {admin ? "Acesso verificado; ações por implementar" : "Funcionalidade por implementar"}</span></div></section>
      <div className="setup-card"><div><span className="eyebrow muted-eyebrow">SESSÃO</span><h3>Autenticação Iku ativa</h3><p>Login, sessão local, 2FA de administrador e permissões da área de administração estão ligados.</p></div><span className="setup-arrow"><ShieldCheck size={18} /></span></div>
    </div>
  );
}
