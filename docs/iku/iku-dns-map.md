# Mapa DNS / serviços do Iku

## Rotas públicas ativas

- `iknowu.org` e `www.iknowu.org` servem o site público do Iku.
- `app.iknowu.org` serve o portal Iku e as páginas de autenticação.
- `cloud.iknowu.org` serve o Nextcloud através do túnel Cloudflare `iku-public-vps` e do Nginx do site público.

As portas web da VPS permanecem fechadas; o Cloudflare Tunnel é a entrada pública destas rotas.

## Rotas privadas ativas

- `https://vps-4e5174e4.tail2931da.ts.net:8443/` serve o n8n através do Tailscale Serve, do encaminhamento local `iku-n8n-forward` e do serviço ClusterIP `n8n.iku.svc.cluster.local:5678`.
- As APIs internas do Iku, a API LFM3 e os restantes serviços administrativos permanecem privados na Tailscale ou dentro do cluster. A página de login do portal é pública; as rotas autenticadas e administrativas exigem sessão Iku.

O caminho público `iknowu.org/n8n` abre atualmente a landing page do Iku; não encaminha para o n8n. O hostname `n8n.iknowu.org` não está configurado como rota ativa. Usa o endereço privado da Tailscale acima.

## Rotas planeadas

Estes serviços não fazem parte da entrada pública atual e não devem ser tratados como rotas ativas:

- `gitlab.iknowu.org`
- `ai.iknowu.org`
- `confy.iknowu.org`
- `webui.iknowu.org`
- `grafana.iknowu.org`

Não publiques um serviço apenas adicionando um registo DNS. É necessário configurar a entrada correspondente no Cloudflare Tunnel e no proxy, e documentar a política de acesso.
