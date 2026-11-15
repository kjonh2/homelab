# Iku Responsive Layout System

## Objetivo
O UI do Iku é o mesmo em todas as plataformas, mas adapta a disposição ao tamanho do ecrã.

## Breakpoints
### Mobile
- `< 600px`
- 1 coluna
- menu em drawer ou bottom nav
- cards empilhados
- ações principais sempre visíveis

### Tablet
- `600px - 1023px`
- 2 colunas
- sidebar compacta ou colapsada
- cards em grelha média
- listas com previews laterais

### Desktop
- `1024px - 1439px`
- sidebar completa
- 2 a 3 colunas
- painéis laterais permanentes
- navegação sempre visível

### Widescreen
- `>= 1440px`
- 3 a 4 colunas
- dashboard denso
- mais conteúdo simultâneo
- suporte para admin e observabilidade lado a lado

## Regras de layout
- o conteúdo prioritário nunca fica escondido atrás de menus
- ações críticas aparecem no topo ou no primeiro card
- o menu adapta-se, mas os nomes não mudam
- cards e botões mantêm a mesma identidade visual
- listas longas viram tabelas só em desktop

## Comportamento por secção
### Login
- mobile: formulário único por coluna
- desktop: formulário central com painel lateral de status

### Dashboard
- mobile: resumo em cartões empilhados
- tablet: métricas e atalhos em 2 colunas
- desktop: overview com widgets
- widescreen: mais detalhe e side panels

### Devices
- mobile: lista vertical
- desktop: tabela com estado e ações

### Downloads
- mobile: cartões com botão grande
- desktop: grid/table com versão e hash

### Admin
- mobile: ainda acessível, mas mais compacto
- desktop/widescreen: painéis densos, com filtros e logs

## Regra de ouro
Muda o layout, não a identidade.
