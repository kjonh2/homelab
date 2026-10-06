package com.iknowu.app

import android.content.Context
import android.content.SharedPreferences

/**
 * PIN opcional para as categorias protegidas (Medical e Segurança).
 *
 * Guardado em SharedPreferences (SHA-256 do PIN). Se ainda não existe,
 * a 1ª entrada na categoria pergunta se o utilizador quer definir um PIN
 * (pode escolher "Sem PIN" — escolha guardada e a categoria deixa de pedir).
 */
object FilePinManager {

    private const val PREFS = "files_pin_prefs"
    private const val KEY_HASH = "pin_hash"
    private const val KEY_CHOSEN = "pin_chosen"

    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** O utilizador já decidiu sobre o PIN (definido ou recusado)? */
    fun hasDecided(context: Context): Boolean = prefs(context).contains(KEY_CHOSEN)

    /** Existe um PIN definido? */
    fun hasPin(context: Context): Boolean = prefs(context).getString(KEY_HASH, null) != null

    /** Define um novo PIN (guarda SHA-256). */
    fun setPin(context: Context, pin: String) {
        prefs(context).edit()
            .putString(KEY_HASH, sha256(pin))
            .putBoolean(KEY_CHOSEN, true)
            .apply()
    }

    /** Escolha por não definir PIN ("Sem PIN") — a categoria deixa de pedir. */
    fun chooseNoPin(context: Context) {
        prefs(context).edit().putBoolean(KEY_CHOSEN, true).apply()
    }

    /** Verifica o PIN introduzido. */
    fun verifyPin(context: Context, pin: String): Boolean =
        prefs(context).getString(KEY_HASH, null) == sha256(pin)

    /** Remove o PIN (nova escolha na próxima entrada). */
    fun clearPin(context: Context) {
        prefs(context).edit().remove(KEY_HASH).remove(KEY_CHOSEN).apply()
    }

    private fun sha256(value: String): String = try {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        digest.digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    } catch (_: Exception) {
        value // fallback improvável
    }
}
