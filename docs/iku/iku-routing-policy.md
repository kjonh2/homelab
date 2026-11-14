# Iku routing policy

## Rotas públicas

- `iknowu.org` serve a landing page pública do Iku.
- `app.iknowu.org` serve o portal e as páginas de login; as rotas autenticadas e administrativas são protegidas pelo Iku Auth.
- `cloud.iknowu.org` serve o Nextcloud através do Cloudflare Tunnel e do Nginx do site público.

## Rotas privadas

- O n8n está disponível em `https://vps-4e5174e4.tail2931da.ts.net:8443/`, através do Tailscale Serve e de um encaminhamento local para o serviço ClusterIP.
- O LFM3 e as restantes APIs administrativas permanecem privados na Tailscale ou no cluster Kubernetes.

Não uses `iknowu.org/n8n` como endereço do n8n: esse caminho abre atualmente o site público. `n8n.iknowu.org` não é uma rota ativa. O editor e os webhooks do n8n estão configurados para o endereço privado da Tailscale.

## Rotas futuras

Uma futura rota pública para serviços como Confy ou WebUI precisa de configuração correspondente no proxy/túnel e de uma política de acesso definida antes de se adicionar DNS. Uma resposta HTTP 200 da landing page não comprova que o serviço está encaminhado para esse caminho.
