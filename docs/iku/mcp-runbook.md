# Iku / Drisa MCP Runbook

Última verificação: 2026-11-14.

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

## Segurança

- Não anexes exports de perfil, dados OAuth nem credenciais ao repositório ou à conversa.
- Nunca uses o perfil amplo `kiko` para a Drisa.
- As alterações ao perfil aplicam-se à próxima sessão do Docker MCP Gateway. Reinicia o processo agente consumidor se continuar a mostrar a lista antiga.
- Não instales o Docker MCP Toolkit na homelab ou na VPS, a menos que um agente vá correr nessas máquinas e precise do seu próprio perfil.
