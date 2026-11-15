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

Esta VPS suporta os serviços de portal, automação e cloud observados junto com **um servidor de modelo LFM3**. As variantes Omni, texto e uncensored podem ser selecionadas, mas os números medidos não provam que possam servir pedidos simultaneamente; com 8 GiB e sem swap, manter apenas um modelo ativo é a configuração conservadora. O modelo de texto atualmente selecionado é `lfm3-uncensored`.

O endpoint LLM atual é um serviço `llama.cpp` privado que serve GGUFs do LFM3/Unsloth, com um modelo residente por vez. Não é o Unsloth Studio. O Studio pode fazer chat CPU com GGUF, mas a documentação oficial reserva treino e exportação para GPU; a VPS não tem GPU e já opera perto do limite de memória quando Kokoro está ativo. Por isso, não se instala um segundo servidor Studio em paralelo: uma migração só deve avançar depois de medir espaço de memória ou aumentar os recursos da VPS. [Unsloth Studio](https://github.com/unslothai/unsloth#unsloth-studio-web-ui) · [requisitos oficiais](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements).

Reverificação live em 2026-11-15 05:42 Europe/Paris: `free -h` reportou 649 MiB disponíveis; `kubectl top node` mostrou 6746 MiB usados (87%) e 2224m CPU (55%). O áudio VPS usava 2978 MiB e o servidor LFM3 1248 MiB. LFM3, Drisa audio VPS, Nextcloud, n8n e portal estavam `1/1 Ready`. Este estado não tem margem para acrescentar uma segunda instância Unsloth Studio com segurança.

Em 2026-11-12, a API autenticada `/models` mostrou `lfm3-uncensored` carregado; `/health` e `/models` responderam HTTP 200. A configuração da Drisa aponta para esta API da VPS. Este estado substitui a nota anterior sobre o modelo Omni em execução; Omni e texto continuam a ser opções selecionáveis, com apenas um modelo residente de cada vez.

### Medição comparativa LFM3 — 2026-11-14

As três variantes foram carregadas e medidas sequencialmente na VPS, sem modelos concorrentes. Cada pedido não streaming pediu um parágrafo em português europeu, com limite de 160 tokens e temperatura 0,2. Os tokens/s abaixo dividem os tokens de conclusão pelo tempo total HTTP; incluem pré-processamento e latência do router, por isso são estimativas de throughput percebido e não velocidade pura de descodificação.

| Modelo | Tokens de conclusão | Tempo total | Estimativa de parede |
|---|---:|---:|---:|
| `lfm3-uncensored` | 144 | 10,01 s | 14,4 tokens/s |
| `lfm3-text` | 134 | 9,58 s | 14,0 tokens/s |
| `lfm3-omni` | 160 | 11,38 s | 14,1 tokens/s |

Os testes usaram pedidos de texto; não medem entrada de áudio nem o percurso completo da Drisa. Depois dos testes, `lfm3-uncensored` foi restaurado como modelo selecionado e uma chamada final respondeu HTTP 200. A VPS mantém `--models-max 1`, pelo que só um destes modelos fica residente de cada vez.

Na verificação adicional de 2026-11-14, o modelo já carregado `lfm3-uncensored` gerou 128 tokens em streaming: TTFT 1,35 s, descodificação 7,73 s (16,6 tokens/s) e 9,08 s para o pedido completo (14,1 tokens/s de parede). Este pedido curto confirma a rota e dá uma medição atual do modelo selecionado; não substitui a comparação anterior das três variantes. Logo após a chamada, o pod LFM3 usava 2061 MiB e o nó VPS estava a 64% de memória e 44% de CPU.

Na medição de 2026-11-11, o cluster tinha um nó. A situação mudou em 2026-11-12: o cluster tem agora dois nós Ready, com a VPS como único control plane e o homelab como worker tainted. Isto não fornece alta disponibilidade do control plane. As PVCs usam armazenamento local e não substituem backups. O estado mais recente está abaixo.

Em 2026-11-12, a partir do portátil ligado ao tailnet, o portal redirecionou `/` para `/login` (307) e `/login` respondeu 200; n8n `/healthz`, Nextcloud `/status.php` e LFM3 `/health` responderam 200 nas portas privadas `8443`, `8444` e `8445`. Isto confirma as rotas HTTPS tailnet-only em funcionamento. Os Services Kubernetes continuam ClusterIP; estes resultados não substituem a auditoria das regras públicas do firewall.

## Segurança observada

- `sshd` tem `PermitRootLogin no`, `PasswordAuthentication no`, `PubkeyAuthentication yes` e `X11Forwarding no`.
- UFW está ativo com entrada negada por defeito. SSH é limitado por taxa; as regras adicionais permitem os CIDRs internos de Pods e Services.
- Verificado em 2026-11-14: as portas TCP `5432`, `6443`, `8443`–`8445` e `10250` falharam em probes aos endereços públicos IPv4 e IPv6. K3s API `6443`, Flannel UDP `8472` e kubelet `10250` só aceitam o nó homelab em `tailscale0`; PostgreSQL TCP `5432` só aceita o portátil pela interface Tailscale. Os listeners do host em `6443` e `10250` não significam exposição pública.
- `unattended-upgrades` está ativo; não havia reinício pendente durante a verificação.
- `fail2ban` está inativo; a proteção de SSH observada é a regra `LIMIT` do UFW combinada com autenticação por chave.

## Estado do cluster após expansão — 2026-11-12

Medição de `kubectl top` após o homelab entrar como worker e o site estático ser distribuído pelos dois nós:

- VPS: 4 vCPU e 8 GiB; 150m CPU (3%) e 4095 MiB de memória usados (52%). O LFM3 usa 855 MiB neste instante e a configuração mantém apenas um modelo carregado.
- Homelab: Intel Pentium J3710 de 4 cores e 7,6 GiB; 271m CPU (6%) e 3144 MiB de memória usados (40%). Aloja o servidor Restic e uma réplica Nginx/Cloudflare do site.
- `iku-public-site` está `2/2 Running` em cada réplica: uma no nó VPS e outra no homelab. `iknowu.org/` e `app.iknowu.org/login` devolveram 200 pela Cloudflare; cada conector registou quatro ligações HTTP/2. A ligação QUIC UDP falhou na pré-verificação, pelo que o cloudflared continua através de HTTP/2.
- Auth, portal, PostgreSQL, Nextcloud, n8n e LFM3 continuam no VPS. O homelab é backup/worker, não control plane de substituição; o failover completo do site durante indisponibilidade do VPS ainda não foi testado.

## Revalidação do cluster — 2026-11-14

Via SSH Tailscale à VPS, ambos os nós reportaram `Ready` em K3s `v1.37.2+k3s1`; `vps-4e5174e4` é control plane e `homelab` é worker. Todos os pods de aplicação estavam `Running` e sem reinícios; os Jobs concluídos de backup/restore estavam `Completed`; os 11 PVCs estavam `Bound`. Após o pedido de benchmark LFM3, `lfm3-server` usava 2061 MiB e o pod de áudio 3 MiB. A amostra `kubectl top` indicou VPS 1770m CPU/4981 MiB (44%/64%) e homelab 691m/2174 MiB (17%/27%); os valores são instantâneos.

Na mesma revalidação, as rotas públicas `iknowu.org/`, `app.iknowu.org/login` e `cloud.iknowu.org/index.php/login` responderam HTTP 200. As rotas privadas da VPS também responderam 200: n8n `/healthz` na 8443, Nextcloud `/status.php` na 8444 e LFM3 `/health` na 8445. Isto confirma disponibilidade HTTP, não a autenticação interativa nem o SSO do Nextcloud.

## Revalidação da firewall e políticas de rede — 2026-11-15

Inspeção ao estado ativo da VPS via Tailscale SSH: UFW está `active`, com entrada `deny`, saída `allow` e encaminhamento `deny`; TCP 22 tem `LIMIT` em IPv4/IPv6. As exceções IPv4 permitem os CIDRs K3s `10.42.0.0/16` e `10.43.0.0/16`; as portas K3s 6443, 8472/UDP e 10250 só permitem o endereço tailnet do homelab na interface `tailscale0`. PostgreSQL 5432 só permite o portátil `100.78.120.84` em `tailscale0`, ligado ao endereço local VPS `100.67.97.92`. Não há regra UFW de entrada geral para as portas HTTPS de serviços; o acesso público continua a ser feito pelas rotas Cloudflare verificadas acima. `kubectl get networkpolicies -A` confirmou políticas instaladas para áudio Drisa, PostgreSQL Drisa, ingress de Auth/Portal/LFM3/n8n/Nextcloud e os três componentes do namespace de backup. Esta verificação confirma presença/configuração do firewall e das políticas; não é um teste de penetração nem valida cada fluxo permitido/negado da NetworkPolicy.

Nova verificação em 2026-11-15 via SSH Tailscale: ambos os nós continuam `Ready`, os nove pods da namespace `iku` estão `Running` sem reinícios e os 11 PVCs estão `Bound`. `kubectl top nodes` marcou VPS em 121m CPU (3%) e 4980 MiB (64%) e homelab em 227m CPU (5%) e 2413 MiB (30%). As seis rotas HTTP públicas/privadas acima voltaram a responder 200.
