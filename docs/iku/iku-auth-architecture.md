# Iku Auth — arquitetura de implementação

## Estado atual

O `iku-auth` está instalado no VPS e o primeiro administrador concluiu o bootstrap com TOTP. A aplicação Android foi ligada ao serviço por uma ponte que valida o Firebase ID token e emite uma sessão Iku; a APK atual foi instalada e o hash do pacote instalado coincide com o build local. A sessão Android ainda requer confirmação no ecrã Perfil. O portal exige sessão e falha fechado; Nextcloud, n8n e LFM3 ainda mantêm autenticação própria. O tailnet dá transporte privado, não sessão Iku nem SSO.

## Objetivos

- Uma identidade local para o portal, a app Android e as APIs Iku.
- Sessões e permissões controladas pelo Iku, com revogação e auditoria.
- TOTP obrigatório para administradores.
- Tokens de API distintos por dispositivo e com scopes mínimos.
- Não depender do Firebase para autorizar acesso aos dados e serviços Iku.

## Componentes e fronteiras

```text
Browser ── HTTPS/Tailscale ── Iku Portal ── ClusterIP ── Iku Auth ── SQLite PVC
Android ── HTTPS/Tailscale ───────────────────────────────┘
Traefik/auth gateway ── valida sessão/claims ── Nextcloud, n8n e outros serviços
```

- `iku-auth`: API privada no namespace `iku`; uma réplica, sem NodePort ou Ingress público.
- `auth-db`: SQLite separado dos dados Nextcloud, guardado num PVC e copiado em backups cifrados.
- `iku-portal`: formulário e páginas de conta; comunica com a API de auth apenas no servidor Next.js.
- Android: a ponte Firebase → Iku está implementada; tokens de sessão ficam cifrados com Android Keystore. O login Firebase continua como prova de identidade durante a migração.
- Gateway: valida sessão ou token e aplica roles/scopes antes de encaminhar pedidos.

O cluster VPS atual é de nó único com armazenamento local. Por isso a base de dados começa com uma réplica e não oferece failover. O worker homelab pode alojar workloads sem estado; não mover a base de dados entre nós sem primeiro definir armazenamento replicado e backups com recuperação testada.

## Identidade e migração Android

- Email e palavra-passe local são a forma principal de autenticação.
- O Auth cria as sessões Iku, aplica roles, MFA e revogação. Um Firebase ID token nunca vale como sessão Iku nem como autorização de serviço.
- Durante a migração, o botão Google pode continuar como prova de identidade externa: o Auth verifica o token e troca-o por uma sessão Iku local; a autorização continua a vir das tabelas Iku. Remover esse caminho apenas depois de confirmar o primeiro login local no Android.
- Não habilitar registo público. Criar a primeira conta `admin` através de um token aleatório de bootstrap, de uso único, fornecido por Secret e removido depois de concluído.
- O admin tem de configurar TOTP antes de receber uma sessão com privilégios. Guardar os segredos TOTP cifrados e guardar hashes dos códigos de recuperação.

## Sessões, tokens e proteção

- Sessão web opaca, aleatória e revogável, persistida como hash no banco de dados; cookie `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, com expiração limitada e rotação após autenticação/MFA.
- Verificar `Origin` nas mutações web e usar token CSRF. Nunca aceitar credenciais ou tokens em query strings.
- Android recebe access token de curta duração e refresh token rotativo. Guardar hash do refresh token, família, dispositivo, expiração e revogação; guardar o segredo apenas no Keystore no cliente.
- Tokens de API têm prefixo identificável, hash no banco, nome de dispositivo, scopes, criação, última utilização, expiração e revogação. Mostrar o valor apenas uma vez.
- Hash de palavra-passe com Argon2id e parâmetros atualizáveis; comparação de tempo constante para tokens. Limitar tentativas por IP e identificador, sem registar palavras-passe, códigos MFA ou tokens. A ponte Firebase valida assinatura RS256, issuer, audience, timestamps, provider e email verificado, usando certificados Google em cache; não consulta a revogação do refresh token Firebase.
- Chaves de assinatura, credenciais bootstrap e chaves de cifragem chegam por Kubernetes Secret montado como ficheiro. Não usar ConfigMap, imagem, manifestos versionados ou logs para material secreto.

## Modelo de dados

`users`, `roles`, `user_roles`, `mfa_factors`, `recovery_codes`, `sessions`, `refresh_tokens`, `firebase_identities`, `api_tokens`, `audit_events`, `login_attempts`.

Guardar timestamps UTC e IDs aleatórios. Aplicar chaves estrangeiras e índices para utilizador, sessão, dispositivo, expiração e hash do token. Eventos de auditoria registam resultado, ação, utilizador quando conhecido, dispositivo/IP e data, nunca segredos nem conteúdo de prompts.

## API inicial

| Método e rota | Uso |
| --- | --- |
| `POST /v1/auth/bootstrap` | Cria a primeira conta admin e inicia configuração TOTP usando o token de uso único. |
| `POST /v1/auth/bootstrap/verify-mfa` | Confirma TOTP e conclui o bootstrap do administrador. |
| `POST /v1/auth/login` | Valida email/password e TOTP/código de recuperação; cria sessão web ou tokens Android. |
| `GET /v1/auth/session` | Devolve identidade e permissões da sessão atual, sem segredos. |
| `POST /v1/auth/refresh` | Roda refresh token do Android e revoga a utilização anterior. |
| `POST /v1/auth/firebase/exchange` | Verifica Firebase ID token, liga apenas email verificado já provisionado no Iku, exige TOTP do admin e emite sessão Android Iku. |
| `POST /v1/auth/logout` | Revoga a sessão e limpa cookie/token. |

Respostas de autenticação usam mensagens genéricas para não revelar se um email existe. Requerer HTTPS e `Content-Type: application/json`; limitar corpos e tempos de resposta.

## SSO e rollout

Os endpoints atuais de Tailscale Serve expõem diretamente o portal, n8n, Nextcloud e LFM3 em portas separadas. Isso não cria uma sessão comum. Manter a autenticação própria de cada serviço enquanto se instala e verifica o gateway. Depois encaminhar cada serviço através do gateway, bloquear rotas de acesso direto e testar sessão, logout, MFA, permissões e recuperação antes de anunciar SSO. O LFM3 e a Drisa mantêm também os seus tokens de serviço para autenticação máquina-a-máquina.

Rollout incremental:

1. Implementar API, schema, bootstrap de uso único, TOTP, sessões, rate limit e testes de segurança. **Concluído.**
2. Instalar `iku-auth` com PVC e Secrets no VPS. **Concluído; backup Restic diário cifrado para o homelab instalado, integridade verificada e uma base SQLite restaurada com `PRAGMA integrity_check=ok`.**
3. Ligar o portal, verificar a exigência de sessão e concluir o primeiro bootstrap. **Concluído; bootstrap e TOTP confirmados na base de dados da VPS.**
4. Integrar Android com sessão Iku e Keystore; validar migração Google sem tratar Firebase claims como autorização. **Implementado e APK atual instalada; falta o utilizador confirmar a ligação da sessão no Perfil.**
5. Colocar gateway à frente de cada app e só então ativar SSO, RBAC e administração.

## Trade-offs e limites

SQLite reduz consumo e manutenção para o uso single-user atual, mas exige uma réplica e backups consistentes. Um IdP completo como Keycloak ofereceria fluxos OAuth/OIDC prontos, com maior consumo e operação. Reavaliar PostgreSQL/HA quando houver mais utilizadores, concorrência ou necessidade de sobreviver à falha da VPS. O login web, MFA TOTP do administrador, sessões Android e a ponte Firebase estão implementados. Gestão de utilizadores/dispositivos, gateway e SSO continuam por fazer; a retenção/pruning do repositório append-only e exercícios periódicos de recuperação continuam como tarefas operacionais.
