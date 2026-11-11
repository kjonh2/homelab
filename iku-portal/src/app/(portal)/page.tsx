import Link from "next/link";
import { ArrowRight, AudioLines, Boxes, Cloud, Cpu, ShieldCheck, Sparkles } from "lucide-react";
import { PreviewNotice } from "@/components/iku/portal-shell";

const services = [
  { name: "Iku Cloud", detail: "Ficheiros e espaço pessoal", icon: Cloud },
  { name: "Automações", detail: "Workflows com n8n", icon: Boxes },
  { name: "Assistente", detail: "Drisa e agentes LFM3", icon: AudioLines },
];

export default function HomePage() {
  return (
    <div className="home-page">
      <PreviewNotice />
      <section className="hero-card">
        <div className="hero-orb orb-one" /><div className="hero-orb orb-two" />
        <div className="hero-content">
          <div className="eyebrow"><Sparkles size={14} /> A TUA CASA DIGITAL</div>
          <h1>As tuas ferramentas.<br /><span>No teu espaço.</span></h1>
          <p>Um portal privado para aceder aos teus serviços, dispositivos e assistentes a partir de qualquer lugar.</p>
          <div className="hero-actions"><Link className="button button-primary" href="/login">Entrar no Iku <ArrowRight size={16} /></Link><Link className="button button-quiet" href="/services">Explorar serviços</Link></div>
        </div>
        <div className="hero-art" aria-hidden="true"><div className="art-ring ring-back" /><div className="art-ring ring-front" /><div className="art-core"><Sparkles size={38} /></div><span className="art-node node-a"><Cloud size={17} /></span><span className="art-node node-b"><Cpu size={17} /></span><span className="art-node node-c"><ShieldCheck size={17} /></span></div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><span className="eyebrow muted-eyebrow">O TEU ECOSSISTEMA</span><h2>Um ponto de entrada para tudo</h2><p>Os serviços ficam organizados no mesmo espaço, prontos a ligar.</p></div><Link className="text-link" href="/services">Ver serviços <ArrowRight size={15} /></Link></div>
        <div className="service-grid">{services.map(({ name, detail, icon: Icon }) => <article className="service-card" key={name}><div className="service-card-top"><span className="service-icon"><Icon size={19} /></span><span className="status-tag pending"><span className="status-dot" /> A configurar</span></div><h3>{name}</h3><p>{detail}</p><div className="card-divider" /><span className="service-card-foot">Integração pendente <ArrowRight size={14} /></span></article>)}</div>
      </section>

      <section className="bottom-grid">
        <article className="info-card security-card"><div className="info-icon security-icon"><ShieldCheck size={20} /></div><div><h3>Privacidade em primeiro lugar</h3><p>O portal foi pensado para funcionar com autenticação local e acesso privado. A ligação de segurança ainda está por configurar.</p><Link className="text-link" href="/security">Ver plano de segurança <ArrowRight size={15} /></Link></div></article>
        <article className="info-card model-card"><div className="info-icon model-icon"><Cpu size={20} /></div><div><h3>Modelos LFM3</h3><p>Texto e Omni, com um modelo ativo de cada vez na VPS.</p><Link className="text-link" href="/services">Ver estado previsto <ArrowRight size={15} /></Link></div></article>
      </section>
    </div>
  );
}
