import { useState } from "react";

function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 40 40" fill="none">
        <path d="M20 4.5 34 12.6v14.8L20 35.5 6 27.4V12.6L20 4.5Z" stroke="currentColor" strokeWidth="1.4" />
        <path d="M20 11v18M13.3 14.9l13.4 10.2M26.7 14.9 13.3 25.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="20" cy="20" r="3.2" fill="currentColor" />
      </svg>
    </span>
  );
}

function Arrow() {
  return <svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="M4 10h11M10 5l5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  function closeMenu() {
    setMenuOpen(false);
  }

  return (
    <>
      <a className="skip-link" href="#main">Saltar para o conteúdo</a>
      <div className="site-shell">
        <header className="topbar">
          <a className="brand" href="#top" aria-label="Iku, início" onClick={closeMenu}>
            <Mark /><span>iku<span className="brand-dot">.</span></span>
          </a>
          <button
            className="menu-toggle"
            type="button"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            aria-label={menuOpen ? "Fechar navegação" : "Abrir navegação"}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <span /><span />
          </button>
          <nav id="main-navigation" className={menuOpen ? "navigation is-open" : "navigation"} aria-label="Navegação principal">
            <a href="#ecossistema" onClick={closeMenu}>Ecossistema</a>
            <a href="#privacidade" onClick={closeMenu}>Privacidade</a>
            <a href="#sobre" onClick={closeMenu}>Sobre o Iku</a>
            <a className="nav-cta" href="https://app.iknowu.org/login" onClick={closeMenu}>Entrar no Iku <Arrow /></a>
          </nav>
        </header>

        <main id="main">
          <section className="hero" id="top" aria-labelledby="hero-title">
            <div className="hero-copy">
              <div className="eyebrow"><span className="eyebrow-line" /> O TEU ESPAÇO DIGITAL</div>
              <h1 id="hero-title">A tecnologia<br />ao <span>teu ritmo.</span></h1>
              <p className="hero-lede">Iku aproxima os teus serviços, dispositivos e assistente pessoal — num espaço feito para trabalhar contigo.</p>
              <div className="hero-actions">
                <a className="button button-primary" href="#ecossistema">Descobrir o Iku <Arrow /></a>
                <a className="text-link" href="#privacidade">Feito para ser teu <span aria-hidden="true">↘</span></a>
              </div>
              <div className="hero-note"><span className="pulse-dot" /> Um projeto pessoal, em evolução contínua</div>
            </div>

            <div className="hero-art" aria-label="Ilustração da ligação entre a app Iku e a assistente Drisa" role="img">
              <div className="orbit orbit-outer" /><div className="orbit orbit-inner" />
              <div className="orbit-node node-top"><span className="node-glyph glyph-wave">〰</span><span>VOZ</span></div>
              <div className="orbit-node node-right"><span className="node-glyph glyph-grid">▦</span><span>SERVIÇOS</span></div>
              <div className="orbit-node node-bottom"><span className="node-glyph glyph-core">◈</span><span>MODELOS</span></div>
              <div className="orbit-node node-left"><span className="node-glyph glyph-mobile">▯</span><span>APP IKU</span></div>
              <div className="core-card">
                <Mark />
                <strong>Drisa</strong>
                <span className="core-caption">assistente pessoal</span>
                <div className="voice-bars" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><i /><i /></div>
                <span className="core-status"><span className="status-dot" /> pronta a conversar</span>
              </div>
              <div className="floating-label label-a"><span className="tiny-check">✓</span> A tua app</div>
              <div className="floating-label label-b"><span className="tiny-spark">✳</span> O teu ecossistema</div>
            </div>
          </section>

          <section className="trust-strip" aria-label="Princípios do Iku">
            <span>UMA EXPERIÊNCIA</span><i />
            <span>SERVIÇOS LIGADOS</span><i />
            <span>CONTROLO PESSOAL</span>
          </section>

          <section className="ecosystem section" id="ecossistema" aria-labelledby="ecosystem-title">
            <div className="section-heading">
              <div>
                <div className="eyebrow"><span className="eyebrow-line" /> UM ECOSSISTEMA, VÁRIAS POSSIBILIDADES</div>
                <h2 id="ecosystem-title">Tudo conversa.<br /><span>Tu decides.</span></h2>
              </div>
              <p className="section-intro">A app Iku é a porta de entrada para as ferramentas que usas e para a assistente que te acompanha.</p>
            </div>
            <div className="feature-grid">
              <article className="feature-card feature-voice">
                <div className="feature-icon"><WaveIcon /></div>
                <span className="card-index">01 / VOZ</span>
                <h3>Fala com a Drisa</h3>
                <p>Uma experiência de voz que combina transcrição, modelos de linguagem e síntese de fala.</p>
                <div className="pipeline" aria-label="Fluxo de voz: MOSS, LFM3, Kokoro">
                  <span>MOSS</span><b>→</b><span>LFM3</span><b>→</b><span>Kokoro</span>
                </div>
              </article>
              <article className="feature-card feature-models">
                <div className="feature-icon"><NodesIcon /></div>
                <span className="card-index">02 / MODELOS</span>
                <h3>Escolhe o que corre</h3>
                <p>Vê os modelos disponíveis e escolhe onde os carregar, conforme a tarefa e a máquina.</p>
                <div className="model-pills"><span><i /> Texto</span><span><i /> Voz</span><span><i /> Local ou remoto</span></div>
              </article>
              <article className="feature-card feature-services">
                <div className="feature-icon"><ServicesIcon /></div>
                <span className="card-index">03 / SERVIÇOS</span>
                <h3>As tuas ferramentas, juntas</h3>
                <p>Ficheiros, automações e assistência de IA fazem parte do mesmo espaço Iku.</p>
                <div className="service-pills"><span>Nextcloud</span><span>n8n</span><span>LFM3</span></div>
              </article>
            </div>
          </section>

          <section className="privacy section" id="privacidade" aria-labelledby="privacy-title">
            <div className="privacy-visual" aria-hidden="true">
              <div className="privacy-halo halo-one" /><div className="privacy-halo halo-two" />
              <div className="shield"><ShieldIcon /></div>
              <div className="privacy-tag tag-private"><span className="lock-icon">⌑</span> Acesso protegido</div>
              <div className="privacy-tag tag-you"><span className="you-dot" /> Sob o teu controlo</div>
            </div>
            <div className="privacy-copy">
              <div className="eyebrow"><span className="eyebrow-line" /> PRIVACIDADE POR PRINCÍPIO</div>
              <h2 id="privacy-title">O teu espaço.<br /><span>As tuas regras.</span></h2>
              <p>O Iku foi pensado para manter os serviços pessoais atrás de autenticação e dar-te controlo sobre os dispositivos e modelos que usas.</p>
              <ul className="privacy-list">
                <li><span>✓</span> Sessões e serviços protegidos</li>
                <li><span>✓</span> Modelos escolhidos por ti</li>
                <li><span>✓</span> Sem partilhar credenciais na página pública</li>
              </ul>
            </div>
          </section>

          <section className="closing section" id="sobre" aria-labelledby="closing-title">
            <div className="closing-mark"><Mark /></div>
            <div className="eyebrow"><span className="eyebrow-line" /> IKU</div>
            <h2 id="closing-title">Tecnologia que<br /><span>fica do teu lado.</span></h2>
            <p>Um projeto em construção para ligar pessoas, serviços e inteligência artificial de forma simples e pessoal.</p>
            <a className="button button-primary" href="https://app.iknowu.org/login">Entrar no Iku <Arrow /></a>
          </section>
        </main>

        <footer className="footer">
          <a className="brand footer-brand" href="#top"><Mark /><span>iku<span className="brand-dot">.</span></span></a>
          <span>© {new Date().getFullYear()} Iku · Um projeto pessoal</span>
          <a href="#top" className="back-top">Voltar ao topo ↑</a>
        </footer>
      </div>
    </>
  );
}

function WaveIcon() {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 13h2l2.2-6 3.4 13L14 4l3.1 13 2-4H21" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function NodesIcon() {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="5" r="2.3" stroke="currentColor" strokeWidth="1.5"/><circle cx="5" cy="18" r="2.3" stroke="currentColor" strokeWidth="1.5"/><circle cx="19" cy="18" r="2.3" stroke="currentColor" strokeWidth="1.5"/><path d="m10.8 7-4.5 8.8m6.9-8.8 4.5 8.8M7.4 18h9.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>;
}

function ServicesIcon() {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.5"/><rect x="13" y="3" width="8" height="5" rx="2" stroke="currentColor" strokeWidth="1.5"/><rect x="13" y="10" width="8" height="11" rx="2" stroke="currentColor" strokeWidth="1.5"/><rect x="3" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.5"/></svg>;
}

function ShieldIcon() {
  return <svg viewBox="0 0 80 80" fill="none"><path d="M40 8 64 17v18c0 17.4-10.2 28.7-24 37C26.2 63.7 16 52.4 16 35V17l24-9Z" stroke="currentColor" strokeWidth="1.5"/><path d="M29 39.5 36 46l15-16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="40" cy="39" r="24" stroke="currentColor" strokeWidth=".7" strokeDasharray="2 4" opacity=".55"/></svg>;
}

export default App;
