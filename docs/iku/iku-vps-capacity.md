# Capacidade atual da VPS Iku

Medição feita em 2026-11-11 no nó `vps-4e5174e4`, enquanto portal, n8n, Nextcloud e LFM3 estavam ativos.

## Recursos observados

- 4 vCPU Intel Xeon virtualizados (Haswell), sem SMT exposto.
- 8 GiB de RAM; 4.7 GiB disponíveis no host no momento da medição; sem swap configurada.
- Disco raiz de 72 GiB, com 56 GiB livres.
- K3s v1.37.2, embedded SQLite, apenas um nó Ready.
- `kubectl top`: nó com 80m CPU (2%) e 3162 MiB de memória (40%).
- Pods Iku: portal 65 MiB, LFM3 807 MiB, n8n 374 MiB e Nextcloud 180 MiB no instante da medição.
- Todos os quatro pods estavam `1/1 Running`. Os checks HTTP locais devolveram 200 para o portal (`/`), n8n (`/healthz`), Nextcloud (`/status.php`) e LFM3 (`/health`). A rota raiz do LFM3 não é um health check e pode devolver 415.

## Decisão operacional

Esta VPS suporta os serviços de portal, automação e cloud observados junto com **um servidor de modelo LFM3**. O modelo Omni é o servidor atualmente implantado. Os números medidos não provam que os modelos Omni e texto possam servir pedidos simultaneamente; com 8 GiB e sem swap, manter apenas um modelo ativo é a configuração conservadora.

O cluster é um único nó: Kubernetes organiza e reinicia os serviços, mas ainda não fornece alta disponibilidade nem failover entre máquinas. As PVCs usam armazenamento local e não substituem backups. Os outros computadores ainda precisam de autenticação e preparação como workers antes de poderem assumir workloads.

O acesso público continua limitado a SSH (`22/tcp` com rate limit). O K3s API (`6443`) e os serviços web permanecem privados/ClusterIP; Tailscale Serve ainda precisa da aprovação de HTTPS no tailnet antes de os publicar apenas na rede privada.

## Segurança observada

- `sshd` tem `PermitRootLogin no`, `PasswordAuthentication no`, `PubkeyAuthentication yes` e `X11Forwarding no`.
- UFW está ativo: apenas SSH está permitido globalmente, com rate limit; as regras adicionais permitem os CIDRs internos de Pods e Services.
- K3s escuta em `6443` e `10250` no host, mas não há regras UFW públicas para essas portas. Mantém essa distinção ao rever a exposição de rede.
- `unattended-upgrades` está ativo; não havia reinício pendente durante a verificação.
- `fail2ban` está inativo; a proteção de SSH observada é a regra `LIMIT` do UFW combinada com autenticação por chave.
