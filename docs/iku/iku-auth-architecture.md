# Iku Auth — arquitetura final

## Objetivo
Um login local único para todo o Iku, com 2FA, roles e API tokens, para servir:
- `iknowu.org/n8n`
- `iknowu.org/confy`
- `iknowu.org/webui`
- `iknowu.org/cloud`
- áreas admin como `gitlab`, `ai`, `grafana`

## Identidade
- Email + password
- 2FA obrigatório para admin
- sessões web partilhadas
- tokens de API por app/dispositivo

## Roles
- `admin` — acesso total
- `server` — gestão/infra/deploy
- `user` — uso normal
- `api` — integrações e automações

## Fluxo
1. utilizador entra no portal `iknowu.org`
2. autentica no Iku Auth local
3. o portal cria sessão
4. o proxy encaminha para o serviço certo
5. o serviço valida a sessão/claims/headers/token

## Segurança
- 2FA por TOTP ou equivalente
- refresh de sessão
- logout global
- revogação de tokens
- logs de acesso
- rate limiting no login

## Implementação recomendada
- Portal Iku como frontend
- Auth local como backend central
- JWT ou cookie de sessão assinado
- headers internos entre proxy e apps
- roles guardadas no backend
- API tokens separados para Android e automações

## Regras de acesso
- público autenticado: `cloud`, `n8n`, `confy`, `webui`
- admin: `gitlab`, `ai`, `grafana`
- tudo passa pela mesma identidade Iku

## Decisão
O Iku não usa Firebase como auth principal.
Firebase pode ficar só para componentes específicos, mas a identidade principal é local.
