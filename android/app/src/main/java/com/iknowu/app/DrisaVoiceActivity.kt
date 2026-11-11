package com.iknowu.app

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Push-to-talk link to the laptop Drisa gateway over the private Tailscale network. */
class DrisaVoiceActivity : AppCompatActivity() {
    private val prefs by lazy { getSharedPreferences("drisa_voice", MODE_PRIVATE) }
    private val client by lazy {
        OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build()
    }
    private var socket: WebSocket? = null
    private var authenticated = false
    private var recorder: AudioRecord? = null
    private var recordThread: Thread? = null
    private val recording = AtomicBoolean(false)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val recordingLimit = Runnable {
        if (recording.get()) {
            setStatus("Limite de gravação de 2 minutos atingido. A enviar a mensagem.")
            stopRecording()
        }
    }
    private val pcm = ByteArrayOutputStream()
    private lateinit var endpoint: EditText
    private lateinit var deviceId: EditText
    private lateinit var token: EditText
    private lateinit var status: TextView
    private lateinit var transcript: TextView
    private lateinit var connectButton: Button
    private lateinit var talkButton: Button

    private val requestMic = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startRecording() else setStatus("É necessário permitir o microfone para falar com a Drisa.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Drisa"
        buildScreen()
        endpoint.setText(prefs.getString("endpoint", "wss://iknowu.tail2931da.ts.net/"))
        deviceId.setText(prefs.getString("device", "redmi-note-11"))
        token.setText(runCatching { SecureDrisaSettings.load(this) }.getOrNull().orEmpty())
        connectButton.setOnClickListener { if (socket == null) connect() else disconnect() }
        talkButton.setOnClickListener {
            if (recording.get()) stopRecording()
            else if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) startRecording()
            else requestMic.launch(Manifest.permission.RECORD_AUDIO)
        }
        updateButtons()
    }

    private fun buildScreen() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(20))
        }
        fun label(text: String) = TextView(this).apply {
            this.text = text
            textSize = 14f
            setPadding(0, dp(10), 0, dp(4))
        }
        endpoint = EditText(this).apply {
            hint = "wss://iknowu.tailnet.ts.net/"
            setSingleLine(true)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        deviceId = EditText(this).apply { hint = "redmi-note-11"; setSingleLine(true) }
        token = EditText(this).apply {
            hint = "Token da gateway Drisa"
            setSingleLine(true)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        status = label("Desligada")
        connectButton = Button(this).apply { text = "Ligar à Drisa" }
        talkButton = Button(this).apply { text = "Manter premido para falar"; isEnabled = false }
        transcript = TextView(this).apply {
            textSize = 16f
            setPadding(0, dp(12), 0, dp(12))
            setTextIsSelectable(true)
        }
        root.addView(label("Endereço privado da gateway"))
        root.addView(endpoint, matchWrap())
        root.addView(label("Identificador deste telemóvel"))
        root.addView(deviceId, matchWrap())
        root.addView(label("Token da gateway"))
        root.addView(token, matchWrap())
        root.addView(connectButton, matchWrap())
        root.addView(status, matchWrap())
        root.addView(talkButton, matchWrap())
        val scroll = ScrollView(this).apply { addView(transcript) }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
    }

    private fun connect() {
        val url = endpoint.text.toString().trim()
        val id = deviceId.text.toString().trim()
        val secret = token.text.toString().ifBlank {
            runCatching { SecureDrisaSettings.load(this) }.getOrNull().orEmpty()
        }
        if (!url.startsWith("wss://") || id.isBlank() || secret.isBlank()) {
            setStatus("Indica um endereço wss://, o identificador e o token.")
            return
        }
        if (Build.VERSION.SDK_INT < 23) {
            setStatus("A ligação segura requer Android 6.0 ou posterior.")
            return
        }
        try {
            SecureDrisaSettings.save(this, url, id, secret)
        } catch (error: Exception) {
            setStatus("Não foi possível guardar o token com segurança: ${error.message ?: "erro"}")
            return
        }
        token.setText("")
        setStatus("A ligar à gateway privada…")
        val request = Request.Builder().url(url).build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val hello = JSONObject()
                    .put("type", "hello")
                    .put("device_id", id)
                    .put("user", "Kiko")
                    .put("token", secret)
                webSocket.send(hello.toString())
                runOnUiThread { setStatus("Ligada; a autenticar…") }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val message = JSONObject(text)
                    when (message.optString("type")) {
                        "auth" -> {
                            authenticated = message.optBoolean("ok")
                            runOnUiThread {
                                setStatus(if (authenticated) "Ligada e autenticada. Toca no botão para gravar uma mensagem." else "A gateway não autorizou este dispositivo. Confirma a allowlist.")
                                updateButtons()
                            }
                        }
                        "transcript" -> runOnUiThread { appendMessage("Tu", message.optString("text")) }
                        "reply" -> runOnUiThread { appendMessage("Drisa", message.optString("text")) }
                        "tts" -> playReply(message.optString("audio_b64"))
                    }
                } catch (_: Exception) {
                    runOnUiThread { setStatus("A gateway enviou uma resposta inválida.") }
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                authenticated = false
                socket = null
                runOnUiThread {
                    setStatus("Falha na ligação: ${t.message ?: "sem resposta"}. Confirma o Tailscale e o endereço da gateway.")
                    updateButtons()
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                authenticated = false
                socket = null
                runOnUiThread { setStatus("Ligação terminada."); updateButtons() }
            }
        })
        updateButtons()
    }

    private fun disconnect() {
        stopRecording(send = false)
        authenticated = false
        socket?.close(1000, "user disconnected")
        socket = null
        setStatus("Desligada")
        updateButtons()
    }

    private fun startRecording() {
        if (!authenticated || recording.get()) return
        val minBuffer = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (minBuffer <= 0) { setStatus("Este dispositivo não suporta gravação de voz."); return }
        val audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            16000,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBuffer, 8192)
        )
        if (audioRecord.state != AudioRecord.STATE_INITIALIZED) {
            audioRecord.release()
            setStatus("Não foi possível iniciar o microfone.")
            return
        }
        pcm.reset()
        recorder = audioRecord
        recording.set(true)
        talkButton.text = "Parar e enviar voz"
        setStatus("A gravar. Toca novamente quando acabares.")
        mainHandler.postDelayed(recordingLimit, 120_000)
        audioRecord.startRecording()
        recordThread = Thread {
            val buffer = ByteArray(maxOf(minBuffer, 8192))
            while (recording.get()) {
                val count = audioRecord.read(buffer, 0, buffer.size)
                if (count > 0) synchronized(pcm) { pcm.write(buffer, 0, count) }
            }
        }.apply { name = "DrisaAudioCapture"; start() }
    }

    private fun stopRecording(send: Boolean = true) {
        if (!recording.compareAndSet(true, false)) return
        mainHandler.removeCallbacks(recordingLimit)
        try { recorder?.stop() } catch (_: Exception) { }
        try { recordThread?.join(1200) } catch (_: InterruptedException) { Thread.currentThread().interrupt() }
        recorder?.release()
        recorder = null
        recordThread = null
        val bytes = synchronized(pcm) { pcm.toByteArray() }
        if (send && bytes.isNotEmpty() && authenticated) {
            val wav = makeWav(bytes, 16000, 1, 16)
            val message = JSONObject()
                .put("type", "audio")
                .put("audio_b64", Base64.encodeToString(wav, Base64.NO_WRAP))
            if (socket?.send(message.toString()) == true) setStatus("Áudio enviado. A Drisa está a responder…")
            else setStatus("Não foi possível enviar o áudio.")
        }
        updateButtons()
    }

    private fun playReply(encoded: String) {
        try {
            val audioFile = File(cacheDir, "drisa-reply.wav")
            FileOutputStream(audioFile).use { it.write(Base64.decode(encoded, Base64.DEFAULT)) }
            runOnUiThread {
                val player = MediaPlayer()
                player.setOnCompletionListener { it.release(); audioFile.delete() }
                player.setOnErrorListener { mp, _, _ -> mp.release(); audioFile.delete(); true }
                player.setDataSource(audioFile.absolutePath)
                player.prepareAsync()
                player.setOnPreparedListener { it.start() }
            }
        } catch (_: Exception) {
            runOnUiThread { setStatus("Recebi a resposta, mas não consegui reproduzir o áudio.") }
        }
    }

    private fun appendMessage(speaker: String, text: String) {
        transcript.append("$speaker: $text\n\n")
    }

    private fun setStatus(message: String) { status.text = message }

    private fun updateButtons() {
        connectButton.text = if (socket == null) "Ligar à Drisa" else "Desligar"
        talkButton.isEnabled = authenticated || recording.get()
        talkButton.text = if (recording.get()) "Parar e enviar voz" else "Gravar mensagem de voz"
    }

    private fun makeWav(pcmData: ByteArray, sampleRate: Int, channels: Int, bits: Int): ByteArray {
        val byteRate = sampleRate * channels * bits / 8
        val out = ByteBuffer.allocate(44 + pcmData.size).order(ByteOrder.LITTLE_ENDIAN)
        out.put("RIFF".toByteArray(Charsets.US_ASCII)); out.putInt(36 + pcmData.size)
        out.put("WAVE".toByteArray(Charsets.US_ASCII)); out.put("fmt ".toByteArray(Charsets.US_ASCII))
        out.putInt(16); out.putShort(1); out.putShort(channels.toShort()); out.putInt(sampleRate)
        out.putInt(byteRate); out.putShort((channels * bits / 8).toShort()); out.putShort(bits.toShort())
        out.put("data".toByteArray(Charsets.US_ASCII)); out.putInt(pcmData.size); out.put(pcmData)
        return out.array()
    }

    private fun matchWrap() = LinearLayout.LayoutParams(-1, -2)
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        disconnect()
        client.dispatcher.executorService.shutdown()
        super.onDestroy()
    }
}

/** Stores the gateway token encrypted with an Android Keystore AES key. */
private object SecureDrisaSettings {
    fun save(activity: AppCompatActivity, url: String, device: String, token: String) {
        val keyStore = java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "iku.drisa.gateway.token"
        val key = (keyStore.getKey(alias, null) as? java.security.Key) ?: run {
            val generator = javax.crypto.KeyGenerator.getInstance(android.security.keystore.KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            val spec = android.security.keystore.KeyGenParameterSpec.Builder(
                alias,
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or android.security.keystore.KeyProperties.PURPOSE_DECRYPT
            ).setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
            generator.init(spec)
            generator.generateKey()
        }
        val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(javax.crypto.Cipher.ENCRYPT_MODE, key)
        val encrypted = cipher.iv + cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        activity.getSharedPreferences("drisa_voice", AppCompatActivity.MODE_PRIVATE).edit()
            .putString("endpoint", url).putString("device", device)
            .putString("token_encrypted", Base64.encodeToString(encrypted, Base64.NO_WRAP)).apply()
    }

    fun load(activity: AppCompatActivity): String {
        val encoded = activity.getSharedPreferences("drisa_voice", AppCompatActivity.MODE_PRIVATE)
            .getString("token_encrypted", null) ?: return ""
        val packed = Base64.decode(encoded, Base64.NO_WRAP)
        require(packed.size > 12) { "Token guardado inválido" }
        val keyStore = java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val key = keyStore.getKey("iku.drisa.gateway.token", null)
            ?: throw IllegalStateException("Chave segura indisponível")
        val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(javax.crypto.Cipher.DECRYPT_MODE, key, javax.crypto.spec.GCMParameterSpec(128, packed, 0, 12))
        return String(cipher.doFinal(packed, 12, packed.size - 12), Charsets.UTF_8)
    }
}
