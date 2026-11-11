# Iku routing policy

## Público para todos os users
Serviços públicos devem ficar em caminhos sob `iknowu.org/`:
- `iknowu.org/n8n`
- `iknowu.org/confy`
- `iknowu.org/webui`
- `iknowu.org/cloud`

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

## Recomendação de proxy
No proxy:
- `PathPrefix(`/n8n`)` -> n8n
- `PathPrefix(`/confy`)` -> confy
- `PathPrefix(`/webui`)` -> webui
- `PathPrefix(`/cloud`)` -> nextcloud

## Observação
Se a app não suportar subpath direito, usar um redirect curto:
- `iknowu.org/cloud` -> `cloud.iknowu.org`
- `iknowu.org/n8n` -> `n8n.iknowu.org`
