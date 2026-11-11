import { notFound } from "next/navigation";
import { ArrowRight, LockKeyhole } from "lucide-react";
import { PreviewNotice } from "@/components/iku/portal-shell";
import { sectionBySlug } from "@/lib/portal-sections";

export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section: slug } = await params;
  const section = sectionBySlug[slug];
  if (!section) notFound();

  const admin = slug === "admin";
  return (
    <div className="section-page">
      <PreviewNotice />
      <div className="page-heading"><div><span className="eyebrow muted-eyebrow">{admin ? "ACESSO RESTRITO" : "ESPAÇO PESSOAL"}</span><h1>{section.label}</h1><p>{section.description}</p></div>{admin && <span className="status-tag pending"><LockKeyhole size={13} /> Requer autenticação</span>}</div>
      <section className="empty-panel"><div className="empty-icon"><LockKeyhole size={22} /></div><div className="empty-copy"><h2>{admin ? "Área de administração protegida" : "Os teus dados aparecem aqui"}</h2><p>{admin ? "A verificação de sessão e de permissões ainda não está ligada. Esta pré-visualização não executa ações de administração." : "Esta página ainda não está ligada ao serviço de autenticação nem às APIs do homelab. Nenhum dado pessoal é mostrado nesta pré-visualização."}</p><span className="pending-line"><span className="status-dot" /> Backend por configurar</span></div></section>
      <div className="setup-card"><div><span className="eyebrow muted-eyebrow">PRÓXIMO PASSO</span><h3>Ligar o serviço de identidade Iku</h3><p>O blueprint local prevê sessões seguras, 2FA, tokens por dispositivo e auditoria.</p></div><span className="setup-arrow"><ArrowRight size={18} /></span></div>
    </div>
  );
}
