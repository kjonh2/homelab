# Capacidade atual da VPS Iku

Medição feita em 2026-11-11 no nó `vps-4e5174e4`, enquanto portal, n8n, Nextcloud e LFM3 estavam ativos.

## Recursos observados

- 4 vCPU Intel Xeon virtualizados (Haswell), sem SMT exposto.
- 8 GiB de RAM; 4.7 GiB disponíveis no host no momento da medição; sem swap configurada.
- Disco raiz de 72 GiB, com 56 GiB livres.
- K3s v1.37.2, embedded SQLite, apenas um nó Ready naquela medição de 2026-11-11.
- `kubectl top`: nó com 80m CPU (2%) e 3162 MiB de memória (40%).
- Pods Iku: portal 65 MiB, LFM3 807 MiB, n8n 374 MiB e Nextcloud 180 MiB no instante da medição.
- Todos os quatro pods estavam `1/1 Running`. Os checks HTTP locais devolveram 200 para o portal (`/`), n8n (`/healthz`), Nextcloud (`/status.php`) e LFM3 (`/health`). A rota raiz do LFM3 não é um health check e pode devolver 415.

## Decisão operacional

Esta VPS suporta os serviços de portal, automação e cloud observados junto com **um servidor de modelo LFM3**. O modelo Omni é o servidor atualmente implantado. Os números medidos não provam que os modelos Omni e texto possam servir pedidos simultaneamente; com 8 GiB e sem swap, manter apenas um modelo ativo é a configuração conservadora.

Em 2026-11-12, a API autenticada `/models` mostrou `lfm3-uncensored` carregado; `/health` e `/models` responderam HTTP 200. A configuração da Drisa aponta para esta API da VPS. Este estado substitui a nota anterior sobre o modelo Omni em execução; Omni e texto continuam a ser opções selecionáveis, com apenas um modelo residente de cada vez.

Na medição de 2026-11-11, o cluster tinha um nó. A situação mudou em 2026-11-12: o cluster tem agora dois nós Ready, com a VPS como único control plane e o homelab como worker tainted. Isto não fornece alta disponibilidade do control plane. As PVCs usam armazenamento local e não substituem backups. O estado mais recente está abaixo.

Em 2026-11-12, a partir do portátil ligado ao tailnet, o portal redirecionou `/` para `/login` (307) e `/login` respondeu 200; n8n `/healthz`, Nextcloud `/status.php` e LFM3 `/health` responderam 200 nas portas privadas `8443`, `8444` e `8445`. Isto confirma as rotas HTTPS tailnet-only em funcionamento. Os Services Kubernetes continuam ClusterIP; estes resultados não substituem a auditoria das regras públicas do firewall.

## Segurança observada

- `sshd` tem `PermitRootLogin no`, `PasswordAuthentication no`, `PubkeyAuthentication yes` e `X11Forwarding no`.
- UFW está ativo com entrada negada por defeito. SSH é limitado por taxa; as regras adicionais permitem os CIDRs internos de Pods e Services.
- Verificado em 2026-11-14: as portas TCP `5432`, `6443`, `8443`–`8445` e `10250` falharam em probes aos endereços públicos IPv4 e IPv6. K3s API `6443`, Flannel UDP `8472` e kubelet `10250` só aceitam o nó homelab em `tailscale0`; PostgreSQL TCP `5432` só aceita o portátil pela interface Tailscale. Os listeners do host em `6443` e `10250` não significam exposição pública.
- `unattended-upgrades` está ativo; não havia reinício pendente durante a verificação.
- `fail2ban` está inativo; a proteção de SSH observada é a regra `LIMIT` do UFW combinada com autenticação por chave.

## Estado atual do cluster — 2026-11-12

Medição de `kubectl top` após o homelab entrar como worker e o site estático ser distribuído pelos dois nós:

- VPS: 4 vCPU e 8 GiB; 150m CPU (3%) e 4095 MiB de memória usados (52%). O LFM3 usa 855 MiB neste instante e a configuração mantém apenas um modelo carregado.
- Homelab: Intel Pentium J3710 de 4 cores e 7,6 GiB; 271m CPU (6%) e 3144 MiB de memória usados (40%). Aloja o servidor Restic e uma réplica Nginx/Cloudflare do site.
- `iku-public-site` está `2/2 Running` em cada réplica: uma no nó VPS e outra no homelab. `iknowu.org/` e `app.iknowu.org/login` devolveram 200 pela Cloudflare; cada conector registou quatro ligações HTTP/2. A ligação QUIC UDP falhou na pré-verificação, pelo que o cloudflared continua através de HTTP/2.
- Auth, portal, PostgreSQL, Nextcloud, n8n e LFM3 continuam no VPS. O homelab é backup/worker, não control plane de substituição; o failover completo do site durante indisponibilidade do VPS ainda não foi testado.
