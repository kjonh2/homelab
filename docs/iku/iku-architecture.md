# Iku — Arquitetura Única

## Ideia central
O **Iku** é o sistema inteiro.  
O homelab não é um projeto separado: **o homelab é uma instância do Iku**.

## Objetivo
Ter a mesma plataforma Iku nas 3 máquinas:
1. PC atual
2. Homelab
3. VPS OVH

## Stack dentro do Iku
- **Nextcloud**
- **n8n**
- **Confy**
- **llama.cpp**
- **Web UI**
- proxy reverso
- DNS / redirects
- backups
- integrações Cloudflare / GitHub / MCP

## Regra
Cada máquina tem a sua própria instalação do Iku, mas todas seguem:
- a mesma estrutura
- o mesmo nome
- a mesma organização de serviços
- o mesmo runbook base

## Camadas
### 1. Base
- Docker
- Docker Compose
- redes internas
- volumes persistentes

### 2. Serviços
- Nextcloud
- n8n
- Confy
- llama.cpp
- webui

### 3. Acesso
- subdomínios
- Tunnel / proxy
- Cloudflare
- autenticação quando necessária

### 4. Sincronização
- export/import de perfil MCP
- documentação única
- configs espelhadas entre máquinas

## Convenção de nomes
- `iku` = stack principal
- `homelab` = máquina que corre o Iku
- `vps` = máquina remota que também corre o Iku
- `pc` = máquina local que também corre o Iku

## Próximo passo técnico
Consolidar os serviços num único `docker-compose.yml` do Iku e dividir em:
- `iku-core`
- `iku-ai`
- `iku-sync`
- `iku-proxy`

## Resultado esperado
Ao arrancar qualquer uma das 3 máquinas:
- o Iku sobe com os mesmos serviços principais
- o acesso e a estrutura são consistentes
- a diferença é só o hardware e o endpoint

