package com.iknowu.app

import android.content.Context
import android.content.SharedPreferences
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

/**
 * Cliente dos shares de ficheiros do homelab.
 *
 * Fonte configurável: um URL (ex.: http://192.168.1.10:8080/files) que devolve
 * uma listagem — aceita:
 *  - JSON: array de objectos com "name" e opcionalmente "size"
 *    (ou objecto com array em "files");
 *  - HTML: listagem de directório (links <a href>).
 *
 * Os ficheiros são classificados por [FileCategory] e abertos no browser
 * (ACTION_VIEW) — sem download local.
 */
object FileShareClient {

    private const val PREFS = "files_categories_prefs"
    const val KEY_SHARE_URL = "share_url"
    private const val TIMEOUT_S = 8L

    private val client by lazy {
        OkHttpClient.Builder()
            .connectTimeout(TIMEOUT_S, TimeUnit.SECONDS)
            .readTimeout(TIMEOUT_S, TimeUnit.SECONDS)
            .build()
    }

    fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** URL configurado do share do homelab ("" se não configurado). */
    fun shareUrl(context: Context): String =
        prefs(context).getString(KEY_SHARE_URL, "") ?: ""

    fun setShareUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_SHARE_URL, url.trim()).apply()
        FileShareCache.clearCache()
    }

    /** true se existe um share configurado (não garante disponibilidade). */
    fun isConfigured(context: Context): Boolean = shareUrl(context).isNotBlank()

    /** Se aberto localmente só devolve false. */
    fun isHomelabUrl(url: String): Boolean =
        url.startsWith("http://") || url.startsWith("https://")

    /**
     * Obtém os ficheiros do share e devolve os de [category].
     * Chamado em thread de fundo — pode lançar Exception (rede).
     */
    fun listFiles(context: Context, category: FileCategory): List<MediaFileItem> {
        val url = shareUrl(context)
        if (url.isBlank()) return emptyList()
        val cached = FileShareCache.get(category)
        if (cached != null) return cached

        val body = fetch(url)
        val all = parseListing(body, url)
        val filtered = all.filter { FileCategory.classify(it.name) == category }
        FileShareCache.put(category, filtered)
        return filtered
    }

    /** Contagem por categoria (um único pedido HTTP). */
    fun countAll(context: Context): Map<FileCategory, Int> {
        val url = shareUrl(context)
        if (url.isBlank()) return emptyMap()
        return try {
            val all = parseListing(fetch(url), url)
            FileCategory.ALL.associateWith { cat -> all.count { FileCategory.classify(it.name) == cat } }
        } catch (_: Exception) {
            emptyMap()
        }
    }

    private fun fetch(url: String): String {
        val request = Request.Builder().url(url).build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw java.io.IOException("HTTP ${response.code}")
            return response.body?.string().orEmpty()
        }
    }

    /** Analisa a listagem: tenta JSON, depois HTML. */
    private fun parseListing(body: String, baseUrl: String): List<MediaFileItem> {
        if (body.trimStart().startsWith("[") || body.trimStart().startsWith("{")) {
            val parsed = parseJson(body)
            if (parsed.isNotEmpty()) return parsed
        }
        return parseHtml(body, baseUrl)
    }

    private fun parseJson(body: String): List<MediaFileItem> {
        return try {
            val items = ArrayList<MediaFileItem>()
            val root = org.json.JSONObject(body).optJSONArray("files")
                ?: org.json.JSONArray(body)
            for (i in 0 until root.length()) {
                val obj = root.optJSONObject(i) ?: continue
                val name = obj.optString("name").ifBlank { obj.optString("filename") }
                if (name.isNotBlank()) {
                    items.add(
                        MediaFileItem(
                            name = name,
                            sizeBytes = if (obj.has("size")) obj.optLong("size") else -1L,
                            isRemote = true
                        )
                    )
                }
            }
            items
        } catch (_: Exception) {
            emptyList()
        }
    }

    /** Extraí os href de uma listagem HTML de directório. */
    private fun parseHtml(body: String, baseUrl: String): List<MediaFileItem> {
        val items = ArrayList<MediaFileItem>()
        val pattern = Pattern.compile("<a\\s+[^>]*href\\s*=\\s*[\"']([^\"']+)[\"']", Pattern.CASE_INSENSITIVE)
        val matcher = pattern.matcher(body)
        while (matcher.find()) {
            val href = matcher.group(1) ?: continue
            if (href.startsWith("..") || href.startsWith("#") || href.startsWith("javascript")) continue
            val name = java.net.URLDecoder.decode(href.substringAfterLast('/'), "UTF-8").ifBlank { href }
            if (name.isBlank() || name.endsWith("/")) continue
            items.add(MediaFileItem(name = name, sizeBytes = -1L, uri = resolveUrl(baseUrl, href), isRemote = true))
        }
        return items
    }

    private fun resolveUrl(baseUrl: String, href: String): String {
        return try {
            java.net.URI(baseUrl).resolve(href).toString()
        } catch (_: Exception) {
            href
        }
    }
}

/** Cache leve das listagens remotas por categoria (limpa ao mudar URL). */
private object FileShareCache {
    private val cache = java.util.concurrent.ConcurrentHashMap<FileCategory, List<MediaFileItem>>()
    fun get(category: FileCategory): List<MediaFileItem>? = cache[category]
    fun put(category: FileCategory, items: List<MediaFileItem>) {
        cache[category] = items
    }
    fun clearCache() = cache.clear()
}
