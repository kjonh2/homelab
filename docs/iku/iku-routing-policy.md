# Iku routing policy

## Público para todos os users
Serviços públicos devem ficar em caminhos sob `iknowu.org/`, ou num hostname dedicado quando o serviço depende de URLs absolutas ou WebDAV:
- `iknowu.org/n8n`
- `iknowu.org/confy`
- `iknowu.org/webui`
- `cloud.iknowu.org` (Nextcloud)

## Admin / interno
Serviços internos e administrativos devem ficar em subdomínios e exigir login:
- `gitlab.iknowu.org`
- `ai.iknowu.org`
- `grafana.iknowu.org`
- quaisquer APIs privadas

## Regra prática
- Se é para todos os users, usa path-based routing em `iknowu.org/<serviço>`.
- Se é só para admin, usa subdomínio separado com autenticação interna.
- O root `iknowu.org` deve servir a landing/portal do Iku e encaminhar para os serviços públicos.

## Roteamento implementado
- Cloudflare Tunnel `iku-public-vps` encaminha `iknowu.org`, `app.iknowu.org` e `cloud.iknowu.org` ao Nginx público.
- Nginx encaminha `app.iknowu.org` ao portal e `cloud.iknowu.org` ao serviço Nextcloud ClusterIP.
- As portas web do VPS permanecem fechadas; os serviços internos continuam disponíveis apenas pela Tailscale Serve.

## Futuras rotas
No proxy:
- `PathPrefix(`/n8n`)` -> n8n
- `PathPrefix(`/confy`)` -> confy
- `PathPrefix(`/webui`)` -> webui

## Observação
Se a app não suportar subpath direito, usar um redirect curto:
- `iknowu.org/cloud` -> `cloud.iknowu.org`
- `iknowu.org/n8n` -> `n8n.iknowu.org`
