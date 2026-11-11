# Iku DNS / service map

## Root and static
- `iknowu.org` -> existing tunnel / current root routing
- `www.iknowu.org` -> existing CNAME target already configured

## VPS-backed services
These should point to the VPS and be served by the Iku proxy on the VPS:
- `gitlab.iknowu.org`
- `cloud.iknowu.org`
- `n8n.iknowu.org`
- `ai.iknowu.org`
- `confy.iknowu.org`
- `webui.iknowu.org`
- `grafana.iknowu.org`

## Compose routing
Each hostname should map to one container through the proxy:
- `cloud.iknowu.org` -> `iku-nextcloud`
- `n8n.iknowu.org` -> `iku-n8n`
- `ai.iknowu.org` -> `iku-ai`
- `webui.iknowu.org` -> `iku-webui`
- `confy.iknowu.org` -> `iku-confy`
- `grafana.iknowu.org` -> `iku-grafana`
- `gitlab.iknowu.org` -> GitLab container / upstream

## Rule
Do not invent extra public hostnames unless they are in the DNS records.
If a record exists in Cloudflare as an `A` or `CNAME`, the compose and proxy must use the same hostname.
