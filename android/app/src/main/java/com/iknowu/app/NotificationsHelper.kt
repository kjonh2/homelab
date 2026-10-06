package com.iknowu.app

import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import org.json.JSONArray
import org.json.JSONObject

/**
 * Gestor simples de notificações do homelab.
 *
 * - Interface [NotificationManager] mínima (evita conflito com android.app.NotificationManager).
 * - Store local em SharedPreferences (lista serializada em JSON).
 * - Mostra alertas com NotificationCompat (canal em API 26+).
 */
class NotificationsHelper private constructor(context: Context) {

    /** Interface simples para publicar/gerir alertas do homelab. */
    interface NotificationManager {
        fun push(title: String, message: String, urgent: Boolean = false)
        fun getAll(): List<Item>
        fun clear(id: String? = null)
    }

    data class Item(val id: String, val title: String, val message: String, val urgent: Boolean, val at: Long)

    private val appContext: Context = context.applicationContext
    private val prefs = appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun now(): Long = System.currentTimeMillis()

    val manager: NotificationManager = object : NotificationManager {

        override fun push(title: String, message: String, urgent: Boolean) {
            val item = Item(now().toString(), title, message, urgent, now())
            store(item)
            show(item)
        }

        override fun getAll(): List<Item> = load()

        override fun clear(id: String?) {
            if (id == null) {
                prefs.edit().remove(KEY_ITEMS).apply()
            } else {
                val kept = load().filterNot { it.id == id }
                save(kept)
            }
        }
    }

    // ---- Store local (SharedPreferences + JSON) ----

    private fun store(item: Item) {
        val list = load().toMutableList()
        list.add(0, item)
        if (list.size > MAX_ITEMS) list.subList(MAX_ITEMS, list.size).clear()
        save(list)
    }

    private fun load(): List<Item> {
        val raw = prefs.getString(KEY_ITEMS, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                Item(o.getString("id"), o.getString("title"), o.getString("message"), o.getBoolean("urgent"), o.getLong("at"))
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun save(list: List<Item>) {
        val arr = JSONArray()
        list.forEach {
            arr.put(JSONObject().apply {
                put("id", it.id)
                put("title", it.title)
                put("message", it.message)
                put("urgent", it.urgent)
                put("at", it.at)
            })
        }
        prefs.edit().putString(KEY_ITEMS, arr.toString()).apply()
    }

    // ---- Notificação do sistema ----

    private fun show(item: Item) {
        val ctx = appContext
        ensureChannel(ctx)
        val n = NotificationCompat.Builder(ctx, if (item.urgent) CHANNEL_URGENT else CHANNEL_DEFAULT)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(item.title)
            .setContentText(item.message)
            .setPriority(
                if (item.urgent) NotificationCompat.PRIORITY_HIGH
                else NotificationCompat.PRIORITY_DEFAULT
            )
            .setAutoCancel(true)
            .build()
        try {
            NotificationManagerCompat.from(ctx).notify(item.id.hashCode(), n)
        } catch (_: SecurityException) {
            // Permissão POST_NOTIFICATIONS não concedida (API 33+); o item fica no store local.
        }
    }

    companion object {
        private const val PREFS = "iknowu_notifications"
        private const val KEY_ITEMS = "items"
        private const val CHANNEL_DEFAULT = "homelab_default"
        private const val CHANNEL_URGENT = "homelab_urgent"
        private const val MAX_ITEMS = 50
        private const val MIN_SDK = 21 // suportado: NotificationCompat funciona desde o API 21

        @Volatile
        private var instance: NotificationsHelper? = null

        fun get(context: Context): NotificationsHelper =
            instance ?: synchronized(this) {
                instance ?: NotificationsHelper(context).also { instance = it }
            }

        /** Garante os canais de notificação (obrigatório em API 26+; no-op abaixo disso). */
        fun ensureChannel(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? android.app.NotificationManager ?: return
            if (nm.getNotificationChannel(CHANNEL_DEFAULT) == null) {
                nm.createNotificationChannel(
                    android.app.NotificationChannel(
                        CHANNEL_DEFAULT, "Homelab", android.app.NotificationManager.IMPORTANCE_DEFAULT
                    )
                )
            }
            if (nm.getNotificationChannel(CHANNEL_URGENT) == null) {
                nm.createNotificationChannel(
                    android.app.NotificationChannel(
                        CHANNEL_URGENT, "Homelab Urgente", android.app.NotificationManager.IMPORTANCE_HIGH
                    )
                )
            }
        }
    }
}
