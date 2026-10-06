package com.iknowu.app

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.ContextCompat
import java.io.File
import java.util.concurrent.ConcurrentHashMap

/**
 * Detecção de ficheiros por categoria.
 *
 * Fontes:
 *  - Storage local: MediaStore (Imagens/Vídeo/Áudio/Ficheiros) — requer
 *    READ_EXTERNAL_STORAGE até API 32; sem permissão devolve contagens vazias.
 *  - Shares do homelab: ver [FileShareClient].
 *
 * As contagens são cacheadas por processo; usar [clearCache] depois de refresh.
 */
object MediaFileScanner {

    /** Cache: categoria -> lista de ficheiros. */
    private val cache = ConcurrentHashMap<FileCategory, List<MediaFileItem>>()

    fun clearCache() = cache.clear()

    fun cachedCount(category: FileCategory): Int = cache[category]?.size ?: -1

    /** true se a app tem permissão de leitura do storage externo. */
    fun hasStoragePermission(context: Context): Boolean =
        Build.VERSION.SDK_INT >= 33 ||
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.READ_EXTERNAL_STORAGE
            ) == PackageManager.PERMISSION_GRANTED

    /**
     * Varre o MediaStore e devolve os ficheiros de [category].
     * Chamado em thread de fundo — não usar na main thread.
     */
    fun scan(context: Context, category: FileCategory): List<MediaFileItem> {
        cache[category]?.let { return it }

        val result: List<MediaFileItem> = when (category) {
            FileCategory.FOTOS -> scanMediaImages(context)
            FileCategory.VIDEO -> scanMediaCollection(
                context, MediaStore.Video.Media.getContentUri("external"),
                MediaStore.Video.Media._ID, MediaStore.Video.Media.DISPLAY_NAME,
                MediaStore.Video.Media.SIZE
            )
            FileCategory.AUDIO -> scanMediaCollection(
                context, MediaStore.Audio.Media.getContentUri("external"),
                MediaStore.Audio.Media._ID, MediaStore.Audio.Media.DISPLAY_NAME,
                MediaStore.Audio.Media.SIZE
            )
            else -> scanAllFiles(context, category)
        }
        cache[category] = result
        return result
    }

    private fun scanMediaImages(context: Context): List<MediaFileItem> =
        scanMediaCollection(
            context, MediaStore.Images.Media.getContentUri("external"),
            MediaStore.Images.Media._ID, MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.SIZE
        )

    /** Consulta genérica de uma colecção do MediaStore (imagens/vídeo/áudio). */
    private fun scanMediaCollection(
        context: Context,
        uri: Uri,
        colId: String,
        colName: String,
        colSize: String
    ): List<MediaFileItem> {
        if (!hasStoragePermission(context)) return emptyList()
        val items = ArrayList<MediaFileItem>()
        val projection = arrayOf(colId, colName, colSize)
        try {
            context.contentResolver.query(uri, projection, null, null, "$colName ASC")?.use { c ->
                val iId = c.getColumnIndexOrThrow(colId)
                val iName = c.getColumnIndexOrThrow(colName)
                val iSize = c.getColumnIndexOrThrow(colSize)
                while (c.moveToNext()) {
                    items.add(
                        MediaFileItem(
                            name = c.getString(iName) ?: "?",
                            sizeBytes = c.getLong(iSize),
                            uri = ContentUris.withAppendedId(uri, c.getLong(iId)).toString()
                        )
                    )
                }
            }
        } catch (_: SecurityException) {
            return emptyList()
        } catch (_: Exception) {
            return emptyList()
        }
        return items
    }

    /**
     * Categorias sem colecção dedicada (Docs, Medical, Finanças, Segurança):
     * varre a tabela geral de ficheiros do MediaStore e classifica por extensão
     * e palavras-chave no nome/caminho; fallback para varrimento de ficheiros
     * nas pastas comuns (Download/Documents) quando o MediaStore não devolve nada.
     */
    private fun scanAllFiles(context: Context, category: FileCategory): List<MediaFileItem> {
        val items = ArrayList<MediaFileItem>()
        val uri = MediaStore.Files.getContentUri("external")
        try {
            context.contentResolver.query(
                uri,
                arrayOf(MediaStore.Files.FileColumns._ID, MediaStore.Files.FileColumns.DATA, MediaStore.Files.FileColumns.SIZE),
                null, null, null
            )?.use { c ->
                val iId = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns._ID)
                val iData = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DATA)
                val iSize = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.SIZE)
                while (c.moveToNext()) {
                    val data = c.getString(iData) ?: continue
                    if (!FileCategory.classify(data).let { it == category }) continue
                    items.add(
                        MediaFileItem(
                            name = data.substringAfterLast('/'),
                            sizeBytes = c.getLong(iSize),
                            uri = ContentUris.withAppendedId(uri, c.getLong(iId)).toString()
                        )
                    )
                }
            }
        } catch (_: Exception) {
            // segue para o fallback
        }
        if (items.isNotEmpty()) {
            return items.sortedBy { it.name.lowercase() }
        }
        return scanFallbackDirectories(category)
    }

    /** Fallback: varrimento directo de pastas comuns (sem MediaStore). */
    private fun scanFallbackDirectories(category: FileCategory): List<MediaFileItem> {
        val items = ArrayList<MediaFileItem>()
        val base = Environment.getExternalStorageDirectory()
        val dirs = listOf(
            File(base, "Download"), File(base, "Downloads"), File(base, "Documents"),
            File(base, "Documentos"), File(base, "Medical"), File(base, "Financas"),
            File(base, "Backup")
        ).filter { it.exists() && it.isDirectory }
        dirs.forEach { dir ->
            dir.listFiles()?.forEach { f ->
                if (!f.isFile) return@forEach
                val path = f.absolutePath
                if (FileCategory.classify(path) == category) {
                    items.add(MediaFileItem(name = f.name, sizeBytes = f.length(), uri = Uri.fromFile(f).toString()))
                }
            }
        }
        return items.sortedBy { it.name.lowercase() }
    }
}
