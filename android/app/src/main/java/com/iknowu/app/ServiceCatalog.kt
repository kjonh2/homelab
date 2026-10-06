package com.iknowu.app

/**
 * Catálogo dos serviços apresentados no bloco "Atalhos de serviços".
 *
 * Para adicionar um novo serviço basta acrescentar uma entrada à lista:
 *     ServiceItem(id, nome, url, descricao, estado, estadoOk)
 * A grelha de cards gera-se automaticamente a partir desta lista.
 *
 * Os URLs são configuráveis: altera-os aqui (ou liga-os a settings remotas
 * no futuro) sem tocar no fragmento.
 */
object ServiceCatalog {

    // URLs base configuráveis — editar aqui para apontar às instâncias reais.
    const val URL_HERMES: String = "https://hermes.nousresearch.com"
    const val URL_GRAFANA: String = "http://localhost:3000"
    const val URL_N8N: String = "http://localhost:5678"

    // TODO(Kiko): preencher com os URLs reais das instâncias / páginas de gestão.
    const val URL_OPENCLAW: String = "http://IP_DO_SERVIDOR:PORTA/openclaw"
    const val URL_OPENCODE: String = "http://IP_DO_SERVIDOR:PORTA/opencode"
    const val URL_ANTIGRAVITY: String = "http://IP_DO_SERVIDOR:PORTA/antigravity"
    const val URL_MCPS: String = "http://IP_DO_SERVIDOR:PORTA/mcps"

    val servicos: List<ServiceItem> = listOf(
        ServiceItem(
            id = "hermes",
            nome = "Hermes",
            url = URL_HERMES,
            descricao = "Agente de IA",
            estado = "Online",
            estadoOk = true
        ),
        ServiceItem(
            id = "grafana",
            nome = "Grafana",
            url = URL_GRAFANA,
            descricao = "Dashboards e métricas",
            estado = "Online",
            estadoOk = true
        ),
        ServiceItem(
            id = "n8n",
            nome = "N8N",
            url = URL_N8N,
            descricao = "Automatização de fluxos",
            estado = null,
            estadoOk = true
        ),
        ServiceItem(
            id = "openclaw",
            nome = "OpenClaw",
            url = URL_OPENCLAW,
            descricao = "Claw Cloud",
            estado = null,
            estadoOk = true
        ),
        ServiceItem(
            id = "opencode",
            nome = "OpenCode",
            url = URL_OPENCODE,
            descricao = "Agente de código",
            estado = null,
            estadoOk = true
        ),
        ServiceItem(
            id = "antigravity",
            nome = "Antigravity",
            url = URL_ANTIGRAVITY,
            descricao = "IDE com IA",
            estado = null,
            estadoOk = true
        ),
        ServiceItem(
            id = "mcps",
            nome = "MCPs",
            url = URL_MCPS,
            descricao = "Gestão de MCP servers",
            estado = null,
            estadoOk = true
        )
        // Exemplo de nova entrada:
        // ServiceItem("homeassistant", "Home Assistant", "http://IP_DO_SERVIDOR:8123", "Casa", "Online", true)
    )
}
