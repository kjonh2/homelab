# Iku Portal — estrutura

## Objetivo
`iknowu.org` é o portal principal do utilizador:
- login
- perfil
- devices
- configs
- downloads
- sessões
- serviços
- admin quando aplicável

## Navegação principal
### Público / sessão
- Home
- Login
- Ajuda
- Estado do sistema

### Após login
- Dashboard
- Perfil
- Devices
- Configs
- Downloads
- Serviços
- Sessões
- Segurança
- Support

### Admin
- Users
- Roles
- Tokens
- Audit logs
- Deploys
- Health

## Páginas
### `/`
Landing page com:
- branding Iku
- CTA login
- status rápido
- atalhos públicos

### `/login`
Login local Iku:
- email/password
- Google opcional se quiseres manter
- 2FA
- switch account

### `/dashboard`
Resumo do utilizador:
- nome
- roles
- devices
- última sessão
- downloads recentes
- avisos de segurança

### `/profile`
Perfil do user:
- dados pessoais
- avatar
- emails ligados
- preferências

### `/devices`
Lista dos devices:
- Android
- Windows
- Linux
- browser sessions
- last seen
- revoke device

### `/configs`
Configurações do user:
- tema
- idioma
- notificações
- permissões
- sync

### `/downloads`
Downloads do build atual:
- APK
- EXE
- DEB
- AppImage
- links por versão

### `/releases`
Histórico de versões:
- changelog
- build number
- data
- artefactos

### `/services`
Serviços do Iku:
- cloud
- n8n
- confy
- webui
- admin services

### `/sessions`
Sessões ativas:
- device
- IP
- hora
- revogar

### `/security`
Segurança:
- 2FA
- recovery codes
- password
- API tokens

## Menu lateral
- Dashboard
- Profile
- Devices
- Configs
- Downloads
- Releases
- Services
- Sessions
- Security
- Admin

## Regra de acesso
- tudo o que é user normal aparece após login
- admin só aparece com role
- downloads são públicos autenticados por sessão
- cada user vê só os seus devices/configs/tokens

## Downloads por plataforma
- Android -> APK
- Windows -> EXE
- Debian/Ubuntu -> DEB
- opcional -> AppImage, MSI, DMG

## Comportamento desejado
- o portal é a casa do user
- as apps são serviços dentro da casa
- os artefactos de build vivem no portal
- o login é único para tudo
