# Iku — estratégia de updates sem reiniciar tudo

## Regra principal
O Iku deve ser dividido em **serviços independentes**, para que um update afete só o que mudou.

## Como fazer
### 1. Um compose por bloco
Separar em ficheiros:
- `iku-proxy.yml`
- `iku-core.yml`
- `iku-ai.yml`
- `iku-sync.yml`

### 2. Um container por serviço
Cada serviço corre no seu próprio container:
- Nextcloud
- n8n
- Confy
- llama.cpp
- Web UI
- proxy
- DB
- cache
- observability

### 3. Volumes persistentes
Os dados nunca vivem no container:
- bancos em volumes
- uploads em volumes
- configs em volumes
- modelos de IA em volumes

### 4. Recriar só o serviço alterado
Quando houver update:
- mudar só o compose do serviço
- fazer `docker compose up -d --no-deps --force-recreate <serviço>`
- evitar `down` global

### 5. Dependências explícitas
Se um serviço muda:
- não reiniciar a DB se só mudou a UI
- não reiniciar o proxy se só mudou o backend interno
- não reiniciar o restante stack

## Ordem de deploy
1. atualizar imagens
2. subir o serviço alvo
3. validar healthcheck
4. só depois, se preciso, reload do proxy

## Exemplo
- Update do n8n → reinicia só `iku-n8n`
- Update do Nextcloud → reinicia só `iku-nextcloud`
- Update do Web UI → reinicia só `iku-webui`
- Update do proxy → reload do `iku-proxy` sem tocar nos outros

## Regra de ouro
**Nunca usar `docker compose down` para manutenção normal.**  
Só usar para migrações grandes ou limpeza total.

## Objetivo
Updates frequentes devem ser:
- rápidos
- isolados
- sem derrubar o resto do Iku
