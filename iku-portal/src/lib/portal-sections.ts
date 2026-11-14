export type PortalSection = {
  slug: string;
  label: string;
  description: string;
  icon: string;
};

export const portalSections: PortalSection[] = [
  { slug: "dashboard", label: "Painel", description: "Estado geral do teu espaço Iku.", icon: "layout" },
  { slug: "profile", label: "Perfil", description: "Os teus dados e preferências.", icon: "user" },
  { slug: "devices", label: "Dispositivos", description: "Dispositivos ligados à tua conta.", icon: "devices" },
  { slug: "settings", label: "Configurações", description: "Tema, idioma, notificações e sincronização.", icon: "settings" },
  { slug: "downloads", label: "Transferências", description: "Aplicações e artefactos de versão.", icon: "download" },
  { slug: "releases", label: "Versões", description: "Histórico de builds e alterações.", icon: "release" },
  { slug: "services", label: "Serviços", description: "Os serviços disponíveis no teu homelab.", icon: "services" },
  { slug: "sessions", label: "Sessões", description: "Sessões ativas e dispositivos recentes.", icon: "sessions" },
  { slug: "security", label: "Segurança", description: "Autenticação, fatores e tokens.", icon: "security" },
  { slug: "admin", label: "Administração", description: "Gestão reservada a administradores.", icon: "admin" },
];

export const sectionBySlug = Object.fromEntries(
  portalSections.map((section) => [section.slug, section]),
) as Record<string, PortalSection>;
