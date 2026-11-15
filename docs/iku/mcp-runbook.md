# Iku / Drisa MCP Runbook

Última verificação: 2026-11-15.

## Modelo de instalação

- O Docker MCP Toolkit corre neste portátil Windows, onde está o agente Drisa/Hermes. A homelab e a VPS expõem os serviços; não precisam de cópias do perfil MCP do portátil.
- Usa o perfil `drisa` para o agente. Mantém o perfil pessoal `kiko` separado; não exportes nem atribuas as permissões mais amplas desse perfil à Drisa.
- O perfil `drisa` contém apenas `github-official`, `obsidian` e `youtube_transcript`, com ferramentas de leitura. Não contém Cloudflare Docs nem permite escrita no GitHub, escrita/eliminação no Obsidian, shell, ciclo de vida de containers ou deployment.
- O perfil é gerido pelo Docker MCP Toolkit e guardado na configuração local do utilizador. Foi guardada uma cópia em `C:\Users\kjonh\workspace\drisa\backups\`; não a incluas no repositório, pois pode conter configuração local.
- As skills estão instaladas em `C:\Users\kjonh\.hermes\skills\drisa-docker-mcp\` e `C:\Users\kjonh\.hermes\skills\drisa-context-management\`.

## Verificar o perfil

```powershell
docker mcp profile list
docker mcp profile show drisa
python deploy/windows/inspect_drisa_mcp_profile.py drisa
```

O script de inspeção mostra apenas nomes de ferramentas marcadas como leitura. Para mudar a lista permitida, usa `docker mcp profile tools drisa` e volta a inspecionar as ferramentas exportadas. Guarda uma cópia privada antes de editar o perfil.

O verificador valida a allowlist ativa de cada servidor, não a lista completa de ferramentas do catálogo. Em 2026-11-14, confirmou 23 ferramentas GitHub com indicação `readOnly`, nove ferramentas Obsidian de pesquisa/leitura e quatro ferramentas de transcrição/metadados do YouTube. Qualquer ferramenta não aprovada, ou um servidor ausente, faz o comando falhar.

## Conteúdo do perfil

- `github-official`: leitura de repositórios, ficheiros, commits, issues e pull requests.
- `obsidian`: pesquisa, listagem e leitura; append, patch e delete estão desativados.
- `youtube_transcript`: leitura de transcrições e metadados de vídeos.

## Estado da gateway

O perfil local continua disponível para inspeção, mas o handshake da gateway ainda não foi validado. Em 2026-11-14, com Docker MCP CLI `v0.44.3` e `McpManagementService` em execução, `docker pass ls` listou os identificadores locais sem ler valores. Em contraste, `docker mcp secret ls` devolveu `deadline_exceeded` ao chamar `ResolverService/GetSecrets`. Isso confirma que os identificadores existem no armazenamento local; a falha está no caminho do resolver MCP, mas a causa interna ainda não foi identificada. O serviço já foi iniciado com UAC e o timeout persiste. Um `docker mcp gateway run --profile drisa --dry-run --verbose` anterior também ficou à espera do resolver. Não exportes os segredos para ficheiros como tentativa de contorno.

As skills Docker MCP e gestão de contexto estão instaladas em `%LOCALAPPDATA%\hermes\skills\` e `%USERPROFILE%\.hermes\skills\`; os ficheiros instalados têm o mesmo SHA-256 que as versões versionadas em `deploy/windows/skills/`. O `mcp_servers.drisa-docker` está ativo em `%LOCALAPPDATA%\hermes\config.yaml`, lança `docker mcp gateway run --profile drisa`, e limita a sessão à allowlist acima. O handshake real continua por validar.

Nova verificação em 2026-11-14: Docker MCP CLI `v0.44.3`, Docker client/server `29.9.3`, perfil `drisa` com três servidores e 36 ferramentas permitidas. `McpManagementService` está `Running` como `LocalSystem`; reiniciá-lo não corrigiu o timeout de `docker mcp secret ls`, que continua a devolver `deadline_exceeded` em `ResolverService/GetSecrets`. Os logs Hermes mostram a mesma falha ao iniciar `drisa-docker`. Não exportes nem copies os segredos para contornar o resolver. Um reinício completo do Docker Desktop continua por aprovar.

Revalidação em 2026-11-15 antes do reinício: Docker Desktop `4.99.0.245822` e Docker MCP CLI `v0.44.3`; `docker desktop status` reportava `running`. `docker mcp secret ls` falhou com timeout em `ResolverService/GetSecrets`. `docker ps` não devolveu resposta e foi interrompido após a espera; `docker desktop diagnose` também não produziu relatório após mais de dois minutos e foi interrompido. A recolha não foi carregada nem partilhada. O reinício autorizado e o resultado posterior estão abaixo.

Após o reinício autorizado em 2026-11-15, `docker desktop status` voltou a `running`, `docker version` respondeu com client/server `29.9.3` e `docker ps` confirmou 42 containers em execução. Duas chamadas a `docker mcp secret ls` após o Desktop estar pronto ainda expiraram no mesmo `ResolverService/GetSecrets`. Assim, o reinício recuperou o engine mas não o resolver de segredos; não foram feitas mais tentativas de reinício nem se leram valores dos segredos.

Follow-up em 2026-11-15: Docker MCP CLI `v0.44.3`; `docker mcp profile list` e `docker mcp profile show drisa` responderam, e o perfil continua a identificar os três servidores aprovados. Uma nova chamada a `docker mcp secret ls`, com a saída integral descartada, voltou a expirar. O Docker Desktop permanece `running`; não foi reiniciado outra vez e nenhum valor de segredo foi lido.

Revalidação posterior em 2026-11-15: o perfil e a configuração local continuam legíveis. `docker desktop status` indica `running` e o endpoint Engine `/_ping` responde HTTP 200, mas `docker ps` não termina após 20 segundos e `GET /v1.41/containers/json?all=0` não devolve cabeçalhos em 5 segundos. `docker inspect` por ID continua a responder, pelo que o Engine não está totalmente inacessível. `docker mcp secret ls` continua a falhar com `deadline_exceeded` em `ResolverService/GetSecrets`. Os logs recentes do Desktop mostram timeouts ao iniciar verificações de saúde e mensagens TTRPC sobre streams inativos. O diagnóstico local, sem `--upload`, não terminou após cerca de dois minutos; não foi enviado nem partilhado. Isto confirma uma degradação do Engine e do resolver, mas não identifica a causa. Não leias nem exportes os segredos, não pares containers para recuperar a listagem e não reinicies o Desktop sem combinar a interrupção dos serviços locais.

Revalidação às 05:18 Europe/Paris em 2026-11-15: `docker mcp profile list`, `docker mcp profile show drisa` e `docker mcp tools list` responderam; o engine reporta versão `29.9.3`. Os perfis guardados são `kiko`, `mygithub` e `drisa`; o perfil Drisa tem apenas `github-official`, `obsidian` e `youtube_transcript`. O perfil `homelabagent` descrito na nota histórica do Obsidian não existe no conjunto atual. `docker ps` continuou pendurado por mais de 25 segundos e foi interrompido apenas no cliente; não reiniciei o Engine. Não consultei nem imprimi valores de segredos. A nota do Obsidian sobre `homelabagent` deve ser tratada como histórica até o perfil ser reconstruído com as ligações e autorizações atuais.

Nova verificação às 05:51 Europe/Paris em 2026-11-15: `docker info --format '{{.ServerVersion}}'` respondeu `29.9.3`, mas `docker ps` continuou sem resposta por mais de 25 segundos e foi interrompido no cliente. A listagem de perfis e de ferramentas MCP continua responsiva; `homelabagent` continua ausente. A nota histórica do Obsidian descreve sete servidores (Proxmox, Notion, GitHub, SQLite, Node.js sandbox, Next.js devtools e Docker Hub), mas não prova que os endpoints e autorizações atuais ainda coincidam. Mantive o perfil intacto e não consultei valores de segredos nem reiniciei o Docker Desktop.

O upstream tem uma [issue aberta no `docker/mcp-gateway`](https://github.com/docker/mcp-gateway/issues/551) que também relata `deadline_exceeded` em `ResolverService/GetSecrets` persistente após reinícios do Desktop. O relato é de macOS e Docker MCP `v0.43.3`, portanto é apenas um sintoma semelhante, não uma causa confirmada para este Windows com `v0.44.3`. Não foi aplicado nenhum contorno que copie ou contorne os segredos.

## Segurança

- Não anexes exports de perfil, dados OAuth nem credenciais ao repositório ou à conversa.
- Nunca uses o perfil amplo `kiko` para a Drisa.
- As alterações ao perfil aplicam-se à próxima sessão do Docker MCP Gateway. Reinicia o processo agente consumidor se continuar a mostrar a lista antiga.
- Não instales o Docker MCP Toolkit na homelab ou na VPS, a menos que um agente vá correr nessas máquinas e precise do seu próprio perfil.

## Catálogo e carregamento de modelos Drisa

Em 2026-11-15, o gateway Drisa do portátil deixou de usar o resolver Docker MCP para os catálogos e carregamento de modelos no PC. Usa `GET /api/models/local` e `GET /api/inference/loaded-models` para texto, `GET /api/inference/audio/catalog?source=cache` para TTS, e as APIs nativas de load/speech do Unsloth. O STT do PC continua a usar a API audio.cpp. Um teste WSS autenticado confirmou os catálogos PC/VPS/homelab e os indicadores `loaded`; o Docker MCP continua degradado para ferramentas/secrets do agente, mas já não bloqueia a lista de modelos na app Iku.
