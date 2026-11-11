import Link from "next/link";
import { ArrowRight, Cloud, Cpu, ShieldCheck, Sparkles } from "lucide-react";
import { PreviewNotice } from "@/components/iku/portal-shell";
import { ServiceCards } from "@/components/iku/service-cards";
import { getServiceStatus } from "@/lib/services";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const services = await getServiceStatus();
  const online = services.filter((service) => service.state === "online").length;
  return (
    <div className="home-page">
      <PreviewNotice />
      <section className="hero-card">
        <div className="hero-orb orb-one" /><div className="hero-orb orb-two" />
        <div className="hero-content">
          <div className="eyebrow"><Sparkles size={14} /> A TUA CASA DIGITAL</div>
          <h1>As tuas ferramentas.<br /><span>No teu espaço.</span></h1>
          <p>O estado dos serviços da VPS e atalhos privados para os abrir na tua rede Tailscale.</p>
          <div className="hero-actions"><Link className="button button-primary" href="/services">Abrir serviços <ArrowRight size={16} /></Link><Link className="button button-quiet" href="/security">Ver segurança</Link></div>
        </div>
        <div className="hero-art" aria-hidden="true"><div className="art-ring ring-back" /><div className="art-ring ring-front" /><div className="art-core"><Sparkles size={38} /></div><span className="art-node node-a"><Cloud size={17} /></span><span className="art-node node-b"><Cpu size={17} /></span><span className="art-node node-c"><ShieldCheck size={17} /></span></div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><span className="eyebrow muted-eyebrow">ESTADO AGORA</span><h2>{online} de {services.length} serviços da VPS respondem</h2><p>Verificação direta pela rede interna do cluster; os links requerem Tailscale.</p></div><Link className="text-link" href="/services">Detalhes <ArrowRight size={15} /></Link></div>
        <ServiceCards services={services} />
      </section>

      <section className="bottom-grid">
        <article className="info-card security-card"><div className="info-icon security-icon"><ShieldCheck size={20} /></div><div><h3>Privacidade em primeiro lugar</h3><p>O portal foi pensado para funcionar com autenticação local e acesso privado. A ligação de segurança ainda está por configurar.</p><Link className="text-link" href="/security">Ver plano de segurança <ArrowRight size={15} /></Link></div></article>
        <article className="info-card model-card"><div className="info-icon model-icon"><Cpu size={20} /></div><div><h3>Modelos LFM3</h3><p>O estado da API da VPS é atualizado ao carregar o painel. Troca de modelo disponível na app Iku.</p><Link className="text-link" href="/services">Abrir os serviços <ArrowRight size={15} /></Link></div></article>
      </section>
    </div>
  );
}
