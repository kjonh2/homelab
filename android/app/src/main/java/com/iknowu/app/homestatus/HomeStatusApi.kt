package com.iknowu.app.homestatus

import android.os.Handler
import android.os.Looper
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/**
 * Client da API REST do homelab (kjonh2/homelab — stack docker-compose.homelab.yml).
 *
 * Fonte principal: HTTP API do Prometheus (homelab-prometheus, porta 9090 exposta
 * atrás do NPM/Traefik). Métricas de node_exporter/traefik:
 *   - up / count(up)                → estado dos containers/serviços
 *   - node_cpu_seconds_total        → uso de CPU
 *   - node_memory_*_bytes           → uso de RAM
 *   - node_boot_time_seconds        → uptime do anfitrião
 *   - node_filesystem_*_bytes       → discos (uso/capacidade por ponto de montagem)
 *
 * As partilhas de ficheiros (FTP / SMB / NFS) não têm métricas no Prometheus;
 * o estado é sonda TCP configurável via [HomeStatusShare] (catálogo próprio,
 * editável pelo utilizador com [setShares]).
 */
class HomeStatusApi(baseUrl: String = DEFAULT_BASE_URL) {

    data class ServiceStatus(val name: String, val up: Boolean)
    data class HomeSnapshot(
        val containersUp: Int,
        val containersTotal: Int,
        val cpuPercent: Double?,
        val ramPercent: Double?,
        val uptimeSeconds: Double?,
        val services: List<ServiceStatus>,
        val disks: List<DiskUsage>
    )

    data class DiskUsage(
        val mount: String,
        val device: String,
        val usedPercent: Double,
        val usedBytes: Double,
        val totalBytes: Double
    ) {
        val isCritical: Boolean get() = usedPercent > 90.0
    }

    data class HomeStatusShare(
        val name: String,
        val url: String,        // ftp://… , smb://… , nfs://…
        val host: String,
        val port: Int
    )

    private var promBase: HttpUrl = baseUrl.toHttpUrlOrNull()
        ?: HomeStatusApi.DEFAULT_BASE_URL.toHttpUrlOrNull()!!

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .callTimeout(15, TimeUnit.SECONDS)
        .build()

    private val main = Handler(Looper.getMainLooper())

    /** Catálogo de partilhas configurável (FTP/SMB/NFS). */
    @Volatile
    var shares: List<HomeStatusShare> = defaultShares()
        private set

    fun setBaseUrl(url: String) {
        url.toHttpUrlOrNull()?.let { promBase = it }
    }

    fun setShares(list: List<HomeStatusShare>) {
        shares = if (list.isEmpty()) defaultShares() else list
    }

    private fun defaultShares(): List<HomeStatusShare> = listOf(
        // Valores de exemplo — substituir pelos endereços reais do homelab
        HomeStatusShare("Partilha FTP", "ftp://192.168.1.10:2121", "192.168.1.10", 2121)
    )

    /** Resolve o caminho /api/v1/query relativo à base configurada (suporta sub-path do reverse proxy). */
    private fun queryUrl(promQl: String): HttpUrl {
        val base = promBase.toString().trimEnd('/')
        val url = if (base.endsWith("/api/v1")) "$base/query" else "$base/api/v1/query"
        return (url + "?query=" + URLEncoder.encode(promQl, "UTF-8")).toHttpUrlOrNull()!!
    }

    private fun getJson(url: HttpUrl, cb: (JSONObject?, String?) -> Unit) {
        val req = Request.Builder().url(url).header("Accept", "application/json").build()
        client.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                main.post { cb(null, e.message ?: "erro de rede") }
            }

            override fun onResponse(call: Call, resp: Response) {
                val body = try { resp.body?.string() } catch (_: Exception) { null }
                resp.close()
                main.post {
                    if (!resp.isSuccessful || body == null) {
                        cb(null, "HTTP ${resp.code}")
                    } else {
                        try { cb(JSONObject(body), null) } catch (e: Exception) { cb(null, "resposta inválida") }
                    }
                }
            }
        })
    }

    /** Executa uma query PromQL instantânea e devolve [(rótulo, valor)]. */
    private fun query(promQl: String, cb: (List<Pair<JSONObject, Double>>?, String?) -> Unit) {
        getJson(queryUrl(promQl)) { json, err ->
            if (json == null) { cb(null, err); return@getJson }
            try {
                val result = json.getJSONObject("data").getJSONArray("result")
                val out = mutableListOf<Pair<JSONObject, Double>>()
                for (i in 0 until result.length()) {
                    val item = result.getJSONObject(i)
                    val v = item.optString("value", "0 NaN").split(" ").getOrNull(1)?.toDoubleOrNull() ?: Double.NaN
                    out += item to v
                }
                cb(out, null)
            } catch (e: Exception) {
                cb(null, "formato inesperado")
            }
        }
    }

    /**
     * Obtém o estado completo do homelab. [cb] é invocado na thread principal.
     */
    fun fetchSnapshot(cb: (HomeSnapshot?, String?) -> Unit) {
        var done = 0
        var err: String? = null
        var containersUp = 0; var containersTotal = 0
        var cpu: Double? = null; var ram: Double? = null; var uptime: Double? = null
        val services = mutableListOf<ServiceStatus>()
        val disks = mutableListOf<DiskUsage>()

        fun finish() {
            if (done == 4) {
                if (err != null && containersTotal == 0) cb(null, err)
                else cb(HomeSnapshot(containersUp, containersTotal, cpu, ram, uptime, services, disks), err)
            }
        }

        // 1) Serviços/containers ativos
        query("up") { res, e ->
            if (res != null) {
                containersTotal = res.size
                for ((m, v) in res) {
                    val labels = m.optJSONObject("metric") ?: JSONObject()
                    val job = labels.optString("job", "desconhecido")
                    val instance = labels.optString("instance", "")
                    val name = if (instance.isNotBlank() && instance != job) "$job ($instance)" else job
                    services += ServiceStatus(name, v >= 1.0)
                    if (v >= 1.0) containersUp++
                }
            } else err = e
            done++; finish()
        }

        // 2) CPU / RAM / uptime (uma query com OR para poupar pedidos)
        query(
            "avg(100 - avg(rate(node_cpu_seconds_total{mode=\"idle\"}[2m])) by (cpu)) * 100" +
            " or (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100" +
            " or (time() - node_boot_time_seconds)"
        ) { res, e ->
            if (res != null) {
                for ((m, v) in res) {
                    val name = m.optJSONObject("metric")?.optString("__name__") ?: ""
                    if (v.isNaN()) continue
                    when {
                        name.startsWith("node_cpu") -> cpu = v
                        name.startsWith("node_memory") -> ram = v
                        name.startsWith("node_boot") || name.startsWith("time") ->
                            if (v > 60) uptime = v
                    }
                }
                // Fallback quando __name__ não distingue (vetores de OR): ordem de resposta
                if (cpu == null && ram == null && uptime == null && res.isNotEmpty()) {
                    var i = 0
                    for ((_, v) in res) {
                        when (i) { 0 -> cpu = v; 1 -> ram = v; else -> if (v > 60) uptime = v }
                        i++
                    }
                }
            }
            done++; finish()
        }

        // 3) Discos (exclui pseudo-sistemas de ficheiros)
        query(
            "100 * (1 - node_filesystem_avail_bytes{fstype!~\"tmpfs|devtmpfs|overlay|squashfs|nsfs|ramfs\"} " +
            "/ node_filesystem_size_bytes{fstype!~\"tmpfs|devtmpfs|overlay|squashfs|nsfs|ramfs\"})"
        ) { res, e ->
            if (res != null) {
                for ((m, v) in res) {
                    if (v.isNaN()) continue
                    val labels = m.optJSONObject("metric") ?: JSONObject()
                    disks += DiskUsage(
                        mount = labels.optString("mountpoint", "/"),
                        device = labels.optString("device", ""),
                        usedPercent = v,
                        usedBytes = 0.0,
                        totalBytes = 0.0
                    )
                }
                disks.sortByDescending { it.usedPercent }
            }
            done++; finish()
        }

        // 4) Capacidade dos discos
        query("node_filesystem_size_bytes{fstype!~\"tmpfs|devtmpfs|overlay|squashfs|nsfs|ramfs\"}") { res, _ ->
            if (res != null) {
                for ((m, v) in res) {
                    val labels = m.optJSONObject("metric") ?: JSONObject()
                    val mount = labels.optString("mountpoint", "/")
                    val idx = disks.indexOfFirst { it.mount == mount }
                    if (idx >= 0 && !v.isNaN()) {
                        val d = disks[idx]
                        disks[idx] = d.copy(totalBytes = v)
                    }
                }
            }
            done++; finish()
        }
    }

    /**
     * Sonda uma partilha (FTP/SMB/NFS) com um pedido TCP curto para determinar
     * se está acessível. [cb] invocado na thread principal com online/offline.
     */
    fun probeShare(share: HomeStatusShare, cb: (online: Boolean) -> Unit) {
        Thread {
            var online = false
            try {
                java.net.Socket().use { s ->
                    s.connect(java.net.InetSocketAddress(share.host, share.port), 3000)
                    online = s.isConnected
                }
            } catch (_: Exception) {
                online = false
            }
            main.post { cb(online) }
        }.start()
    }

    /** Cancela pedidos pendentes (chamar em onDestroy do fragmento). */
    fun cancelAll() {
        try { client.dispatcher.cancelAll() } catch (_: Exception) {}
    }

    companion object {
        /** Base por omissão — apontar ao Prometheus do homelab (NPM/Traefik expõe /prometheus). */
        const val DEFAULT_BASE_URL = "http://192.168.1.10:9090"
        const val POLL_INTERVAL_MS = 10_000L
    }
}
