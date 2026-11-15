# Iku UI System — único em todas as superfícies

## Objetivo
O UI do Iku deve ser igual em:
- app Android
- site `iknowu.org`
- apps web internas
- downloads/portal
- futuras apps desktop

## Princípios
- mesmo layout base
- mesmas cores
- mesmos ícones
- mesma navegação
- mesmos nomes de secções
- mesma linguagem visual

## Visual
### Tema
- dark by default
- roxo como cor principal
- acentos suaves
- cards escuros
- texto claro
- foco em contraste limpo

### Estrutura
- top bar ou app bar igual
- drawer/menu lateral igual onde couber
- cards com cantos arredondados
- botões consistentes
- estados vazios claros

## Navegação comum
Mesmas secções em todo o lado:
- Home / Dashboard
- Profile
- Devices
- Services
- Downloads
- Sessions
- Security
- Settings
- Admin

## Componentes reutilizáveis
- IkuHeader
- IkuSidebar
- IkuCard
- IkuButton
- IkuStatusChip
- IkuSectionTitle
- IkuDeviceTile
- IkuDownloadTile
- IkuLoginPanel

## Regras
- não inventar layouts diferentes por app
- não mudar nomes de menus entre plataformas
- Android, web e desktop devem parecer a mesma família
- admin usa a mesma base visual, só muda o nível de acesso

## Web
- portal com sidebar
- cards para serviços e downloads
- login igual ao Android em estilo e texto

## Android
- mesma hierarquia
- mesmas cores
- mesmos labels
- mesmo estilo de cards e botões

## Downloads
Os downloads devem aparecer com o mesmo padrão visual:
- nome
- plataforma
- versão
- botão download
- hash/changelog se necessário

## Resultado desejado
O utilizador entra em qualquer superfície do Iku e sente:
- é a mesma app
- só muda o tamanho do ecrã
- a navegação e os nomes são iguais
