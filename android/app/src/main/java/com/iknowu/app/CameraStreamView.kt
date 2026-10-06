package com.iknowu.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import java.io.BufferedInputStream
import java.io.DataInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean

/**
 * CameraStreamView — visualizador MJPEG autónomo e reutilizável
 * para as câmaras USB do PC homelab (stream via mjpeg-streamer,
 * Motion ou ffmpeg HTTP MJPEG: http://<host>:<port>/?action=stream).
 *
 * Uso:
 *   view.start("http://192.168.1.50:8081/?action=stream")
 *   view.stop()
 *
 * Lê o multipart/x-mixed-replace manualmente (HttpURLConnection, sem
 * dependências externas) e desenha cada frame neste View custom.
 * Estética dark/purple: placeholder "Sem sinal" quando inactivo.
 */
class CameraStreamView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var latestFrame: Bitmap? = null
    private var frameTimeMs: Long = 0L
    private val running = AtomicBoolean(false)
    @Volatile private var streamUrl: String? = null
    private var thread: Thread? = null

    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        color = 0xFF9C6BFF.toInt()
    }
    private val bgPaint = Paint().apply { color = 0xFF1D1830.toInt() }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF8E8AA8.toInt()
        textSize = 42f
        textAlign = Paint.Align.CENTER
    }
    private val placeholderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF3A2F5C.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 6f
    }

    /** Inicia o stream MJPEG (idempotente). */
    fun start(url: String) {
        if (running.get() && streamUrl == url) return
        stop()
        streamUrl = url
        running.set(true)
        invalidate()
        thread = Thread({ streamLoop(url) }, "CameraMjpegReader").apply {
            isDaemon = true
            start()
        }
    }

    /** Para o stream e liberta o frame actual. */
    fun stop() {
        running.set(false)
        streamUrl = null
        thread?.interrupt()
        thread = null
        invalidate()
    }

    override fun onDetachedFromWindow() {
        stop()
        super.onDetachedFromWindow()
    }

    private fun streamLoop(url: String) {
        while (running.get() && streamUrl == url && !Thread.currentThread().isInterrupted) {
            var conn: HttpURLConnection? = null
            try {
                conn = (URL(url).openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 5000
                    readTimeout = 15000
                    setRequestProperty("Connection", "close")
                }
                conn.connect()
                val ct = conn.contentType ?: ""
                val reader = if (ct.contains("multipart", ignoreCase = true)) {
                    DataInputStream(BufferedInputStream(conn.inputStream, 64 * 1024))
                } else {
                    // Alguns servidores devolvem um JPEG simples; trata como 1 frame.
                    DataInputStream(BufferedInputStream(conn.inputStream, 64 * 1024))
                }
                val boundary = Regex("boundary=(\\S+)", RegexOption.IGNORE_CASE)
                    .find(ct)?.groupValues?.get(1)?.toByteArray()

                while (running.get() && streamUrl == url && !Thread.currentThread().isInterrupted) {
                    val jpg = if (boundary != null) {
                        readMultipartJpeg(reader, boundary)
                    } else {
                        readJpegByMarker(reader)
                    } ?: continue

                    val bmp = BitmapFactory.decodeByteArray(jpg, 0, jpg.size)
                    if (bmp != null) {
                        latestFrame = bmp
                        frameTimeMs = System.currentTimeMillis()
                        postInvalidate()
                    }
                }
            } catch (e: Exception) {
                // Reconecta após breve pausa (stream caiu / rede instável).
                try {
                    Thread.sleep(1500)
                } catch (_: InterruptedException) {
                    break
                }
            } finally {
                conn?.disconnect()
            }
        }
    }

    /** Lê um bloco JPEG de um stream multipart/x-mixed-replace pela boundary. */
    private fun readMultipartJpeg(reader: DataInputStream, boundary: ByteArray): ByteArray? {
        // Saltar a linha da boundary.
        readLine(reader)
        var header = readLine(reader)
        var contentLength = -1L
        while (!header.isNullOrBlank()) {
            val lower = header.lowercase()
            if (lower.startsWith("content-length:")) {
                contentLength = lower.substringAfter(":").trim().toLongOrNull() ?: -1L
            }
            header = readLine(reader)
        }
        return if (contentLength > 0) {
            val buf = ByteArray(contentLength.toInt())
            reader.readFully(buf)
            buf
        } else {
            readJpegByMarker(reader)
        }
    }

    /** Fallback: procura marcadores SOI/EOI JPEG quando não há Content-Length. */
    private fun readJpegByMarker(reader: DataInputStream): ByteArray? {
        val soi = byteArrayOf(0xFF.toByte(), 0xD8.toByte())
        val eoi = byteArrayOf(0xFF.toByte(), 0xD9.toByte())
        var foundSoi = false
        val buf = ArrayList<Byte>(64 * 1024)
        while (running.get()) {
            val b = reader.read()
            if (b < 0) return null
            buf.add(b.toByte())
            val size = buf.size
            if (!foundSoi && size >= 2 && buf[size - 2] == soi[0] && buf[size - 1] == soi[1]) {
                foundSoi = true
                buf.clear()
                buf.add(soi[0]); buf.add(soi[1])
            } else if (foundSoi && size >= 2 && buf[size - 2] == eoi[0] && buf[size - 1] == eoi[1]) {
                val out = ByteArray(size)
                for (i in 0 until size) out[i] = buf[i]
                return out
            }
        }
        return null
    }

    /** readLine tolerante para cabecalhos multipart (LF ou CRLF). */
    private fun readLine(reader: DataInputStream): String? {
        val sb = StringBuilder()
        while (true) {
            val b = reader.read()
            if (b < 0) return null
            if (b == '\n'.code) {
                if (sb.isNotEmpty() && sb.last() == '\r') sb.setLength(sb.length - 1)
                return sb.toString()
            }
            sb.append(b.toChar())
        }
    }

    // ------------------------------------------------------------------ draw

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0 || h <= 0) return

        canvas.drawRect(0f, 0f, w, h, bgPaint)

        val frame = latestFrame
        if (frame != null && System.currentTimeMillis() - frameTimeMs < 5000) {
            val scale = minOf(w / frame.width, h / frame.height)
            val dw = frame.width * scale
            val dh = frame.height * scale
            val dx = (w - dw) / 2f
            val dy = (h - dh) / 2f
            canvas.drawBitmap(frame, null, RectF(dx, dy, dx + dw, dy + dh), null)
        } else {
            // Placeholder "Sem sinal" dark/purple.
            val cx = w / 2f
            val cy = h / 2f
            canvas.drawCircle(cx, cy - 30f, 70f, placeholderPaint)
            canvas.drawCircle(cx, cy - 55f, 18f, placeholderPaint)
            canvas.drawCircle(cx, cy - 5f, 34f, placeholderPaint)
            canvas.drawText(
                if (running.get()) "A ligar..." else "Sem sinal",
                cx, cy + 90f, textPaint
            )
        }
        canvas.drawRect(2f, 2f, w - 2f, h - 2f, borderPaint)
    }
}
