package com.iknowu.app

import android.content.Context
import android.net.Uri

/** Private service links. The user supplies the VPS MagicDNS HTTPS name once. */
object ServiceCatalog {
    private const val PREFS = "iku_private_services"
    private const val SERVER_URL_KEY = "server_base_url"
    private const val DEFAULT_SERVER_URL = "https://vps-4e5174e4.tail2931da.ts.net"

    fun serverBaseUrl(context: Context): String = context
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        .getString(SERVER_URL_KEY, DEFAULT_SERVER_URL)
        .orEmpty()

    fun saveServerBaseUrl(context: Context, baseUrl: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(SERVER_URL_KEY, baseUrl.trim().trimEnd('/'))
            .apply()
    }

    fun serviceUrl(context: Context, port: Int): String {
        val baseUrl = serverBaseUrl(context)
        if (baseUrl.isBlank()) return ""
        val parsed = Uri.parse(baseUrl)
        val host = parsed.host ?: return ""
        val authority = if (port == 443) host else "$host:$port"
        return parsed.buildUpon()
            .scheme("https")
            .encodedAuthority(authority)
            .path("")
            .clearQuery()
            .fragment(null)
            .build()
            .toString()
            .trimEnd('/')
    }

    fun servicos(context: Context): List<ServiceItem> {
        val configured = serverBaseUrl(context).isNotBlank()
        val pendingLabel = if (configured) "Ligação por verificar" else "Configurar acesso"
        return listOf(
            ServiceItem(
                id = "portal",
                nome = "Iku Portal",
                url = serviceUrl(context, 443),
                descricao = "Painel do teu homelab",
                estado = pendingLabel,
                estadoOk = false
            ),
            ServiceItem(
                id = "cloud",
                nome = "Iku Cloud",
                url = serviceUrl(context, 8444),
                descricao = "Ficheiros e espaço pessoal",
                estado = pendingLabel,
                estadoOk = false
            ),
            ServiceItem(
                id = "n8n",
                nome = "Automações",
                url = serviceUrl(context, 8443),
                descricao = "Workflows com n8n",
                estado = pendingLabel,
                estadoOk = false
            ),
            ServiceItem(
                id = "lfm3",
                nome = "Modelos LFM3",
                url = serviceUrl(context, 8445),
                descricao = "API privada · texto e Omni",
                estado = pendingLabel,
                estadoOk = false
            )
        )
    }
}
