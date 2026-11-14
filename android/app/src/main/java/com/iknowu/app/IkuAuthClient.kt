package com.iknowu.app

import android.app.Activity
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import com.google.firebase.auth.FirebaseUser
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Exchanges an authenticated Firebase user for a short-lived Iku session. */
internal object IkuAuthClient {
    private const val BASE_URL = "https://vps-4e5174e4.tail2931da.ts.net"
    private val jsonType = "application/json; charset=utf-8".toMediaType()
    private val http = OkHttpClient.Builder()
        .callTimeout(12, TimeUnit.SECONDS)
        .build()
    private val mainHandler = Handler(Looper.getMainLooper())

    fun connect(activity: Activity, user: FirebaseUser, completed: (Boolean, String) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            completed(false, "A ligação segura ao Iku requer Android 6 ou superior.")
            return
        }
        val saved = IkuAuthSessionStore.read(activity)
        if (saved != null && saved.optLong("expires_at", 0L) > System.currentTimeMillis() / 1000L + 30) {
            completed(true, "Sessão Iku já ligada.")
            return
        }
        val refreshToken = saved?.optString("refresh_token").orEmpty()
        if (refreshToken.isNotBlank()) {
            refresh(activity, refreshToken) { result ->
                when (result.code) {
                    200 -> {
                        if (IkuAuthSessionStore.save(activity, result.body)) completed(true, "Sessão Iku renovada.")
                        else completed(false, "Não consegui guardar a sessão Iku cifrada neste telemóvel.")
                    }
                    401 -> {
                        IkuAuthSessionStore.clear(activity)
                        getFirebaseToken(activity, user, completed)
                    }
                    else -> completed(false, "O serviço Iku não respondeu. Mantive a sessão Firebase existente.")
                }
            }
        } else {
            getFirebaseToken(activity, user, completed)
        }
    }

    fun logout(activity: Activity, completed: (() -> Unit)? = null) {
        val saved = IkuAuthSessionStore.read(activity)
        val accessToken = saved?.optString("access_token").orEmpty()
        val refreshToken = saved?.optString("refresh_token").orEmpty()
        if (accessToken.isBlank() && refreshToken.isBlank()) {
            IkuAuthSessionStore.clear(activity)
            completed?.invoke()
            return
        }
        val requestBuilder = Request.Builder()
            .url(BASE_URL + "/api/auth/logout")
            .post(JSONObject().put("refresh_token", refreshToken).toString().toRequestBody(jsonType))
            .header("Accept", "application/json")
        if (accessToken.isNotBlank()) requestBuilder.header("Authorization", "Bearer $accessToken")
        val request = requestBuilder.build()
        http.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                activity.runOnUiThread {
                    IkuAuthSessionStore.clear(activity)
                    completed?.invoke()
                }
            }

            override fun onResponse(call: Call, response: Response) {
                response.close()
                activity.runOnUiThread {
                    IkuAuthSessionStore.clear(activity)
                    completed?.invoke()
                }
            }
        })
    }

    /** Rotates a saved Android refresh token without requiring a new Firebase/MFA login. */
    fun refreshSavedSession(context: Context, completed: (Boolean, String) -> Unit) {
        val saved = IkuAuthSessionStore.read(context)
        val refreshToken = saved?.optString("refresh_token").orEmpty()
        if (refreshToken.isBlank()) {
            completed(false, "A sessão Iku expirou. Liga-a novamente em Perfil.")
            return
        }
        refresh(context, refreshToken) { result ->
            when (result.code) {
                200 -> {
                    if (IkuAuthSessionStore.save(context, result.body)) completed(true, "Sessão Iku renovada.")
                    else completed(false, "Não consegui guardar a sessão Iku cifrada neste telemóvel.")
                }
                401 -> {
                    IkuAuthSessionStore.clear(context)
                    completed(false, "A sessão Iku expirou. Liga-a novamente em Perfil.")
                }
                else -> completed(false, "Não foi possível renovar a sessão Iku agora.")
            }
        }
    }

    private fun getFirebaseToken(activity: Activity, user: FirebaseUser, completed: (Boolean, String) -> Unit) {
        user.getIdToken(true).addOnCompleteListener(activity) { task ->
            val firebaseToken = task.result?.token
            if (!task.isSuccessful || firebaseToken.isNullOrBlank()) {
                completed(false, "Não consegui confirmar a identidade Firebase para ligar ao Iku.")
            } else {
                exchange(activity, firebaseToken, null, completed)
            }
        }
    }

    private fun exchange(
        activity: Activity,
        firebaseToken: String,
        totpCode: String?,
        completed: (Boolean, String) -> Unit,
    ) {
        val payload = JSONObject()
            .put("id_token", firebaseToken)
            .put("device_name", "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(100))
        if (!totpCode.isNullOrBlank()) payload.put("totp_code", totpCode.trim())
        post(activity, "/api/auth/firebase/exchange", payload) { result ->
            when {
                result.code == 200 -> {
                    if (IkuAuthSessionStore.save(activity, result.body)) completed(true, "Sessão Iku ligada e guardada cifrada.")
                    else completed(false, "Não consegui guardar a sessão Iku cifrada neste telemóvel.")
                }
                result.code == 428 -> requestTotp(activity, firebaseToken, completed)
                result.code == 401 -> completed(false, "Esta conta ainda não está ligada ao Iku. Usa o mesmo email da conta Iku já configurada.")
                result.code == 403 -> completed(false, "O administrador precisa de concluir primeiro a configuração MFA no portal Iku.")
                else -> completed(false, "O serviço Iku não respondeu. Mantive a sessão Firebase existente.")
            }
        }
    }

    private fun requestTotp(activity: Activity, firebaseToken: String, completed: (Boolean, String) -> Unit) {
        activity.runOnUiThread {
            val input = EditText(activity).apply {
                hint = "Código TOTP ou recuperação"
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                setSingleLine(true)
            }
            val dialog = AlertDialog.Builder(activity)
                .setTitle("Confirmar sessão Iku")
                .setMessage("Introduz o código do autenticador para emitir uma sessão Iku neste dispositivo.")
                .setView(input)
                .setNegativeButton("Agora não") { _, _ -> completed(false, "Sessão Iku não ligada; a sessão Firebase continua ativa.") }
                .setPositiveButton("Confirmar", null)
                .create()
            dialog.setOnShowListener {
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    val code = input.text.toString().trim()
                    if (code.isBlank()) {
                        input.error = "Introduz o código"
                    } else {
                        dialog.dismiss()
                        exchange(activity, firebaseToken, code, completed)
                    }
                }
            }
            dialog.show()
        }
    }

    private fun refresh(context: Context, refreshToken: String, completed: (ApiResult) -> Unit) {
        val payload = JSONObject().put("refresh_token", refreshToken)
        post(context, "/api/auth/refresh", payload, completed)
    }

    private fun post(context: Context, path: String, payload: JSONObject, completed: (ApiResult) -> Unit) {
        val request = Request.Builder()
            .url(BASE_URL + path)
            .post(payload.toString().toRequestBody(jsonType))
            .header("Accept", "application/json")
            .build()
        http.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                mainHandler.post { completed(ApiResult(0, JSONObject())) }
            }

            override fun onResponse(call: Call, response: Response) {
                val result = response.use {
                    val body = it.body?.string().orEmpty()
                    ApiResult(it.code, if (body.isBlank()) JSONObject() else runCatching { JSONObject(body) }.getOrDefault(JSONObject()))
                }
                mainHandler.post { completed(result) }
            }
        })
    }

    private data class ApiResult(val code: Int, val body: JSONObject)
}
