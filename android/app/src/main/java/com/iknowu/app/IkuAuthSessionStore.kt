package com.iknowu.app

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Stores Iku access and refresh tokens encrypted with an Android Keystore key. */
internal object IkuAuthSessionStore {
    private const val PREFS = "iku_auth_session"
    private const val BLOB = "encrypted_session"
    private const val KEY_ALIAS = "iku.auth.session.v1"

    @Synchronized
    fun save(context: Context, response: JSONObject): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return false
        return try {
            val accessToken = response.optString("access_token")
            val refreshToken = response.optString("refresh_token")
            val expiresIn = response.optLong("expires_in", 0L)
            if (accessToken.isBlank() || refreshToken.isBlank() || expiresIn <= 0L) return false

            val session = JSONObject()
                .put("access_token", accessToken)
                .put("refresh_token", refreshToken)
                .put("expires_at", System.currentTimeMillis() / 1000L + expiresIn)
                .put("user", response.optJSONObject("user") ?: JSONObject())

            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
            val encrypted = cipher.doFinal(session.toString().toByteArray(Charsets.UTF_8))
            val blob = cipher.iv + encrypted
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(BLOB, Base64.encodeToString(blob, Base64.NO_WRAP))
                .commit()
        } catch (_: Exception) {
            false
        }
    }

    @Synchronized
    fun read(context: Context): JSONObject? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return null
        return try {
            val encoded = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(BLOB, null)
                ?: return null
            val blob = Base64.decode(encoded, Base64.NO_WRAP)
            if (blob.size <= 12) return null
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, blob.copyOfRange(0, 12)))
            JSONObject(String(cipher.doFinal(blob.copyOfRange(12, blob.size)), Charsets.UTF_8))
        } catch (_: Exception) {
            clear(context)
            null
        }
    }

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(BLOB).apply()
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }
}
