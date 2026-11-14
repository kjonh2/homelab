package com.iknowu.app.homestatus

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.iknowu.app.IkuAuthClient
import com.iknowu.app.IkuAuthSessionStore
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Reads authenticated service health from the private Iku portal API. */
class HomeStatusApi(context: Context) {

    data class ServiceStatus(
        val id: String,
        val name: String,
        val description: String,
        val url: String,
        val label: String,
        val up: Boolean,
    )

    data class HomeSnapshot(val services: List<ServiceStatus>) {
        val servicesUp: Int get() = services.count { it.up }
    }

    private val appContext = context.applicationContext
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .callTimeout(15, TimeUnit.SECONDS)
        .build()
    private val main = Handler(Looper.getMainLooper())

    fun fetchSnapshot(cb: (HomeSnapshot?, String?) -> Unit) {
        fetchSnapshot(cb, refreshOnUnauthorized = true)
    }

    private fun fetchSnapshot(cb: (HomeSnapshot?, String?) -> Unit, refreshOnUnauthorized: Boolean) {
        val accessToken = IkuAuthSessionStore.read(appContext)?.optString("access_token").orEmpty()
        if (accessToken.isBlank()) {
            cb(null, "Liga a sessão Iku em Perfil para consultar o estado dos serviços.")
            return
        }

        val request = Request.Builder()
            .url(STATUS_URL)
            .header("Accept", "application/json")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                main.post { cb(null, "Não foi possível chegar ao portal privado Iku.") }
            }

            override fun onResponse(call: Call, response: Response) {
                val status = response.code
                val body = response.use { it.body?.string().orEmpty() }
                main.post {
                    when {
                        status == 401 && refreshOnUnauthorized -> {
                            IkuAuthClient.refreshSavedSession(appContext) { refreshed, message ->
                                if (refreshed) fetchSnapshot(cb, refreshOnUnauthorized = false)
                                else cb(null, message)
                            }
                        }
                        status == 401 -> cb(null, "A sessão Iku continua inválida. Liga-a novamente em Perfil.")
                        status == 403 -> cb(null, "A sessão Iku não tem acesso ao estado dos serviços.")
                        status !in 200..299 -> cb(null, "O portal Iku respondeu com HTTP $status.")
                        else -> try {
                            val rows = JSONObject(body).getJSONArray("services")
                            val services = (0 until rows.length()).map { index ->
                                val item = rows.getJSONObject(index)
                                ServiceStatus(
                                    id = item.optString("id"),
                                    name = item.optString("name"),
                                    description = item.optString("description"),
                                    url = item.optString("url"),
                                    label = item.optString("label"),
                                    up = item.optString("state") == "online",
                                )
                            }
                            cb(HomeSnapshot(services), null)
                        } catch (_: Exception) {
                            cb(null, "O portal Iku enviou um estado inválido.")
                        }
                    }
                }
            }
        })
    }

    fun cancelAll() {
        client.dispatcher.cancelAll()
    }

    companion object {
        private const val STATUS_URL = "https://vps-4e5174e4.tail2931da.ts.net/api/homelab/status"
        const val POLL_INTERVAL_MS = 10_000L
    }
}
