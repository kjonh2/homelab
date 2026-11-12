# Iku / Drisa MCP Runbook

Última verificação: 2026-11-12.

## Modelo de instalação

- O Docker MCP Toolkit corre neste portátil Windows, onde está o agente Drisa/Hermes. A homelab e a VPS expõem os serviços; não precisam de cópias do perfil MCP do portátil.
- Usa o perfil `drisa` para o agente. Mantém o perfil pessoal `kiko` separado; não exportes nem atribuas as permissões mais amplas desse perfil à Drisa.
- O perfil `drisa` permite leitura do GitHub, pesquisa/leitura do Obsidian, leitura de transcrições do YouTube e ferramentas de documentação Cloudflare. Não permite escrita no GitHub, escrita/eliminação no Obsidian, shell, ciclo de vida de containers nem deployment.
- O perfil é gerido pelo Docker MCP Toolkit e guardado na configuração local do utilizador. Foi guardada uma cópia em `C:\Users\kjonh\workspace\drisa\backups\`; não a incluas no repositório, pois pode conter configuração local.
- As skills estão instaladas em `C:\Users\kjonh\.hermes\skills\drisa-docker-mcp\` e `C:\Users\kjonh\.hermes\skills\drisa-context-management\`.

## Verificar o perfil

```powershell
docker mcp profile list
docker mcp profile show drisa
python deploy/windows/inspect_drisa_mcp_profile.py drisa
```

O script de inspeção mostra apenas nomes de ferramentas marcadas como leitura. Para mudar a lista permitida, usa `docker mcp profile tools drisa` e volta a inspecionar as ferramentas exportadas. Guarda uma cópia privada antes de editar o perfil.

## Conteúdo do perfil

- `github-official`: leitura de repositórios, ficheiros, commits, issues e pull requests.
- `obsidian`: pesquisa, listagem e leitura; append, patch e delete estão desativados.
- `youtube_transcript`: leitura de transcrições e metadados de vídeos.
- `cloudflare-docs`: pesquisa de documentação e guias de migração.

## Segurança

- Não anexes exports de perfil, dados OAuth nem credenciais ao repositório ou à conversa.
- Nunca uses o perfil amplo `kiko` para a Drisa.
- As alterações ao perfil aplicam-se à próxima sessão do Docker MCP Gateway. Reinicia o processo agente consumidor se continuar a mostrar a lista antiga.
- Não instales o Docker MCP Toolkit na homelab ou na VPS, a menos que um agente vá correr nessas máquinas e precise do seu próprio perfil.
