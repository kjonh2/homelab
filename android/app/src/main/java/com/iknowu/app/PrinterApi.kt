package com.iknowu.app

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Controlo da impressora 3D Geeetech i3 Pro W.
 *
 * Endpoints estilo OctoPrint/Klipper, todos configuráveis via [PrinterEndpoints]:
 *  - GET  status  -> estado geral (idle/printing/paused/erro)
 *  - GET  temps   -> temperaturas (hotbed e bico/nozzle)
 *  - GET  job     -> progresso da impressão
 *  - POST start / pause / stop -> comandos
 *
 * A implementação usa HttpURLConnection (sem dependências externas) e corre
 * num executor dedicado, devolvendo sempre os resultados na main thread.
 */
interface PrinterApi {
    /** Estado geral da impressora. */
    data class PrinterStatus(
        val state: String,          // "idle", "printing", "paused", "error", ...
        val printing: Boolean,
        val paused: Boolean
    )

    /** Temperaturas em °C. */
    data class PrinterTemps(
        val bedCurrent: Double,
        val bedTarget: Double,
        val nozzleCurrent: Double,
        val nozzleTarget: Double
    )

    /** Progresso da impressão (0..100). */
    data class PrinterProgress(
        val percent: Int,
        val fileName: String?
    )

    data class CommandResult(val success: Boolean, val message: String? = null)

    fun getStatus(callback: (Result<PrinterStatus>) -> Unit)
    fun getTemps(callback: (Result<PrinterTemps>) -> Unit)
    fun getProgress(callback: (Result<PrinterProgress>) -> Unit)
    fun startPrint(callback: (Result<CommandResult>) -> Unit)
    fun pausePrint(callback: (Result<CommandResult>) -> Unit)
    fun stopPrint(callback: (Result<CommandResult>) -> Unit)
    fun cancelAll()
}

/** Configuração dos endpoints (pode ser alterada em runtime pelo utilizador). */
data class PrinterEndpoints(
    var baseUrl: String = "http://[IP_ADDRESS]",
    var statusPath: String = "/api/printer",
    var tempsPath: String = "/api/printer",
    var jobPath: String = "/api/job",
    var startPath: String = "/api/job",
    var pausePath: String = "/api/job",
    var stopPath: String = "/api/job",
    var apiKey: String? = null,
    var timeoutMs: Int = 5000
)

/** Corpos dos comandos POST (OctoPrint-style, ajustáveis para Klipper). */
data class PrinterCommands(
    var startBody: String = """{"command":"start"}""",
    var pauseBody: String = """{"command":"pause","action":"pause"}""",
    var stopBody: String = """{"command":"cancel"}"""
)

/**
 * Implementação concreta de [PrinterApi] sobre HTTP (HttpURLConnection).
 * Compatível com OctoPrint (GET /api/printer, /api/job; POST /api/job) e
 * tolerante a variações Klipper-style (chaves alternativas no JSON).
 */
class HttpPrinterApi(
    private val endpoints: PrinterEndpoints = PrinterEndpoints(),
    private val commands: PrinterCommands = PrinterCommands()
) : PrinterApi {

    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var cancelled = false

    override fun getStatus(callback: (Result<PrinterApi.PrinterStatus>) -> Unit) {
        executor.execute {
            val result = try {
                val response = httpCall(endpoints.statusPath, "GET", null)
                val json = if (response.isBlank()) JSONObject() else JSONObject(response)
                val state = json.optString(
                    "state",
                    json.optJSONObject("state")?.optString("text") ?: "idle"
                )
                val s = state.lowercase()
                Result.success(
                    PrinterApi.PrinterStatus(
                        state = state.ifBlank { "idle" },
                        printing = s.contains("print") && !s.contains("cancel"),
                        paused = s.contains("paus")
                    )
                )
            } catch (e: Exception) {
                Result.failure(e)
            }
            result.deliver(main, callback)
        }
    }

    override fun getTemps(callback: (Result<PrinterApi.PrinterTemps>) -> Unit) {
        executor.execute {
            val result = try {
                val response = httpCall(endpoints.tempsPath, "GET", null)
                val json = if (response.isBlank()) JSONObject() else JSONObject(response)
                fun obj(vararg keys: String): JSONObject? =
                    keys.firstNotNullOfOrNull { json.optJSONObject(it) }
                val bed = obj("bed", "heater_bed", "tool")
                val tool = obj("tool0", "extruder", "tool")
                fun cur(o: JSONObject?, key: String, alt: String): Double {
                    if (o == null) return Double.NaN
                    var v = o.optDouble(key, Double.NaN)
                    if (v.isNaN()) v = o.optDouble(alt, Double.NaN)
                    return v
                }
                Result.success(
                    PrinterApi.PrinterTemps(
                        bedCurrent = cur(bed, "actual", "temperature"),
                        bedTarget = cur(bed, "target", "target"),
                        nozzleCurrent = cur(tool, "actual", "temperature"),
                        nozzleTarget = cur(tool, "target", "target")
                    )
                )
            } catch (e: Exception) {
                Result.failure(e)
            }
            result.deliver(main, callback)
        }
    }

    override fun getProgress(callback: (Result<PrinterApi.PrinterProgress>) -> Unit) {
        executor.execute {
            val result = try {
                val response = httpCall(endpoints.jobPath, "GET", null)
                val json = if (response.isBlank()) JSONObject() else JSONObject(response)
                val progress = json.optJSONObject("progress")
                val job = json.optJSONObject("job")
                val completion = progress?.optDouble("completion", Double.NaN) ?: Double.NaN
                Result.success(
                    PrinterApi.PrinterProgress(
                        percent = if (completion.isNaN()) 0 else completion.coerceIn(0.0, 100.0).toInt(),
                        fileName = job?.optString("file", job.optString("name", ""))
                            ?.takeUnless { it.isEmpty() }
                    )
                )
            } catch (e: Exception) {
                Result.failure(e)
            }
            result.deliver(main, callback)
        }
    }

    override fun startPrint(callback: (Result<PrinterApi.CommandResult>) -> Unit) =
        post(endpoints.startPath, commands.startBody, callback)

    override fun pausePrint(callback: (Result<PrinterApi.CommandResult>) -> Unit) =
        post(endpoints.pausePath, commands.pauseBody, callback)

    override fun stopPrint(callback: (Result<PrinterApi.CommandResult>) -> Unit) =
        post(endpoints.stopPath, commands.stopBody, callback)

    override fun cancelAll() {
        cancelled = true
        executor.shutdownNow()
    }

    // ------------------------------------------------------------- internals

    private fun post(
        path: String,
        body: String,
        callback: (Result<PrinterApi.CommandResult>) -> Unit
    ) {
        executor.execute {
            val result: Result<PrinterApi.CommandResult> = try {
                httpCall(path, "POST", body)
                Result.success(PrinterApi.CommandResult(true))
            } catch (e: Exception) {
                Result.failure(e)
            }
            result.deliver(main, callback)
        }
    }

    private fun httpCall(path: String, method: String, body: String?): String {
        if (cancelled) throw IllegalStateException("API cancelada")
        val url = URL(endpoints.baseUrl.trimEnd('/') + path)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = endpoints.timeoutMs
            readTimeout = endpoints.timeoutMs
            endpoints.apiKey?.takeIf { it.isNotBlank() }?.let {
                setRequestProperty("X-Api-Key", it)
            }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
        }
        val text: String
        try {
            val stream = try {
                conn.inputStream
            } catch (e: Exception) {
                conn.errorStream ?: throw e
            }
            text = BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
        } finally {
            conn.disconnect()
        }
        return text
    }
}

/** Envia um resultado computado numa worker thread para a main thread via callback. */
private fun <T> Result<T>.deliver(main: Handler, callback: (Result<T>) -> Unit) {
    main.post { callback(this) }
}
