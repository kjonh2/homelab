# Iku DNS / service map

## Root and static
- `iknowu.org` -> existing tunnel / current root routing
- `www.iknowu.org` -> existing CNAME target already configured

## Serviços previstos no VPS
Estes serviços devem ser publicados pelo Cloudflare Tunnel; os registos públicos não devem expor diretamente o IP de origem:
- `gitlab.iknowu.org`
- `cloud.iknowu.org`
- `n8n.iknowu.org`
- `ai.iknowu.org`
- `confy.iknowu.org`
- `webui.iknowu.org`
- `grafana.iknowu.org`

The public `cloud.iknowu.org` hostname is served through the `iku-public-vps` Cloudflare Tunnel. Its ingress targets the Nginx sidecar on port 80, and Nginx proxies only that hostname to the Nextcloud ClusterIP service. Keep the VPS web ports closed; the tunnel is the public ingress.

## Roteamento Kubernetes atual e planeado
- `cloud.iknowu.org` -> `iku-public-vps` tunnel -> public-site Nginx -> `nextcloud.iku.svc.cluster.local:80`
- `n8n.iknowu.org` -> `iku-n8n`
- `ai.iknowu.org` -> `iku-ai`
- `webui.iknowu.org` -> `iku-webui`
- `confy.iknowu.org` -> `iku-confy`
- `grafana.iknowu.org` -> `iku-grafana`
- `gitlab.iknowu.org` -> GitLab container / upstream

## Rule
Do not invent extra public hostnames unless they are in the DNS records.
If a record exists in Cloudflare as an `A` or `CNAME`, the compose and proxy must use the same hostname.
