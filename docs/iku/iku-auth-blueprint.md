# Iku Auth — blueprint implementável

## Componentes
- `auth-service`: backend central de login, MFA, sessões e tokens
- `auth-db`: persistência de users, roles, MFA, sessões, tokens e auditoria
- `session-cookie layer`: cookie httpOnly assinado para web
- `gateway middleware`: valida sessão/claims e injeta headers confiáveis
- `mfa module`: TOTP, recovery codes, reset de 2FA
- `token service`: tokens por app/dispositivo com scopes e revogação
- `admin UI`: gestão de users, roles, sessões, MFA e tokens
- `android client`: login, refresh e uso de token scoped
- `audit/rate-limit`: logs, throttling, alertas

## Modelo de dados
- `users`
- `roles`
- `user_roles`
- `mfa_factors`
- `recovery_codes`
- `sessions`
- `refresh_tokens`
- `api_tokens`
- `audit_events`
- `login_attempts`

## Fluxo de autenticação
1. user entra no portal Iku.
2. auth local valida email/password.
3. se necessário, pede TOTP.
4. sessão web é criada com cookie assinado.
5. gateway valida a sessão e encaminha.
6. Android usa o mesmo login, mas guarda material em secure storage.
7. logout/reset/admin revogam tudo e escrevem auditoria.

## Decisão
- Auth principal é **local**
- Firebase não é a identidade principal
- Admin tem 2FA obrigatório
- API tokens são separados de sessões web
