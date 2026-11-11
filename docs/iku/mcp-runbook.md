# Iku / Drisa MCP Runbook

Objetivo: deixar o mesmo conjunto de MCPs disponível em 3 máquinas:
1. PC atual (Docker MCP Toolkit já instalado)
2. Homelab
3. VPS OVH

## Estado atual
- PC atual: perfil `kiko` exportado em `C:/Users/kjonh/workspace/homelab/docker-mcp-kiko.yaml`
- Homelab: precisa de importar o perfil exportado
- VPS: tem Docker, mas não tem Docker MCP Toolkit instalado

## Perfil base
Usar sempre o perfil:
- `kiko`

## Ficheiro base
- `C:/Users/kjonh/workspace/homelab/docker-mcp-kiko.yaml`

## Máquina 1: PC atual

### Verificar o perfil
```bash
docker mcp profile list
docker mcp profile show kiko --clients --format yaml
docker mcp oauth ls
```

### Limpeza
Se houver OAuth Cloudflare velho:
```bash
docker mcp oauth revoke cloudflare-ai-gateway
docker mcp oauth revoke cloudflare-observability
```

### Servidores úteis no perfil
- `github-official`
- `cloudflare-docs`

## Máquina 2: homelab

### Importar o perfil
```bash
docker mcp profile import kiko C:/Users/kjonh/workspace/homelab/docker-mcp-kiko.yaml
```

### Confirmar
```bash
docker mcp profile list
docker mcp profile show kiko --clients --format yaml
docker mcp oauth ls
```

### Se o Docker MCP Toolkit não estiver instalado
Instalar o Docker Desktop/MCP Toolkit equivalente antes de importar.

## Máquina 3: VPS OVH

### Pré-requisitos
- Docker instalado
- Docker MCP Toolkit instalado
- acesso shell ao VPS

### Passos
1. Instalar/ativar o Docker MCP Toolkit
2. Copiar o ficheiro `docker-mcp-kiko.yaml` para o VPS
3. Importar o perfil:
```bash
docker mcp profile import kiko ./docker-mcp-kiko.yaml
```
4. Confirmar:
```bash
docker mcp profile list
docker mcp profile show kiko --clients --format yaml
docker mcp oauth ls
```

## Regra de sincronização
Sempre que o perfil `kiko` mudar no PC:
1. exportar novamente
2. copiar o YAML para a homelab e VPS
3. re-importar no alvo

## Notas
- Não usar os apps Cloudflare antigos (`cloudflare-ai-gateway`, `cloudflare-observability`) para setup novo.
- Se o OAuth do Docker MCP gerar `Invalid client_id`, o app está obsoleto e deve ser ignorado.
- O objetivo é manter o mesmo perfil base nas 3 máquinas, não autorizações manuais diferentes.

## Ordem recomendada
1. PC atual exportado e limpo
2. Homelab importado
3. VPS preparada
4. Só depois autorizar MCPs novos, se necessário
