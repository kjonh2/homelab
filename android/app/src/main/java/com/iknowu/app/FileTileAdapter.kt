package com.iknowu.app

import android.content.ActivityNotFoundException
import android.content.Intent
import android.view.View
import android.widget.GridLayout
import android.widget.Toast
import androidx.core.content.ContextCompat
import com.iknowu.app.databinding.MediaCategoryTileBinding
import com.iknowu.app.databinding.MediaFileRowBinding

/**
 * Adaptador autónomo da secção de ficheiros por categoria.
 *
 * Dois construtores:
 *  - [popularTiles]: um tile por [FileCategory] (emoji, nome, contagem);
 *  - [popularFicheiros]: uma linha/card por [MediaFileItem] (lista ou grelha).
 *
 * Sem RecyclerView — usa GridLayout, igual ao bloco de serviços, para
 * funcionar em todos os flavors (minSdk 21) sem dependências extra.
 */
object FileTileAdapter {

    /**
     * Cria e adiciona um tile por categoria ao grid.
     * @param contagens contagem de ficheiros por categoria (-1 = a carregar / desconhecida)
     * @param onTileClick chamado quando o utilizador toca num tile
     */
    fun popularTiles(
        grid: GridLayout,
        contagens: Map<FileCategory, Int>,
        onTileClick: (FileCategory) -> Unit
    ) {
        val context = grid.context
        val density = context.resources.displayMetrics.density
        grid.removeAllViews()

        FileCategory.ALL.forEach { categoria ->
            val tileBinding = MediaCategoryTileBinding.inflate(
                android.view.LayoutInflater.from(context), grid, false
            )
            val tile = tileBinding.root as View

            tileBinding.tileEmoji.text = categoria.emoji
            tileBinding.tileNome.text = categoria.label

            val contagem = contagens[categoria] ?: -1
            tileBinding.tileContagem.text = if (contagem >= 0) contagem.toString() else "–"

            // Aviso de PIN nas categorias protegidas
            if (categoria.needsPin) {
                tileBinding.tilePinAviso.visibility = View.VISIBLE
                tileBinding.tilePinAviso.text = "🔒"
            }

            tile.setOnClickListener { onTileClick(categoria) }

            // 2 colunas com peso igual (idêntico ao bloco de serviços)
            val params = GridLayout.LayoutParams(
                GridLayout.spec(GridLayout.UNDEFINED, GridLayout.FILL, 1f),
                GridLayout.spec(GridLayout.UNDEFINED, GridLayout.FILL, 1f)
            )
            params.width = 0
            params.height = GridLayout.LayoutParams.WRAP_CONTENT
            val margem = (density * 8).toInt()
            params.setMargins(margem, margem, margem, margem)
            grid.addView(tile, params)
        }
    }

    /**
     * Cria e adiciona uma linha por ficheiro ao grid.
     * @param duasColunas true para grelha 2 colunas (fotos/vídeo/áudio), false para lista
     */
    fun popularFicheiros(
        grid: GridLayout,
        ficheiros: List<MediaFileItem>,
        duasColunas: Boolean
    ) {
        val context = grid.context
        val density = context.resources.displayMetrics.density
        grid.removeAllViews()

        ficheiros.forEach { ficheiro ->
            val rowBinding = MediaFileRowBinding.inflate(android.view.LayoutInflater.from(context), grid, false)
            val row = rowBinding.root as View

            rowBinding.fileEmoji.text = emojiParaFicheiro(ficheiro.name)
            rowBinding.fileNome.text = ficheiro.name
            val detalhe = tamanhoLegivel(ficheiro.sizeBytes) +
                if (ficheiro.isRemote) " · Homelab" else ""
            rowBinding.fileDetalhe.text = detalhe
            rowBinding.fileDetalhe.visibility = if (detalhe.isBlank()) View.GONE else View.VISIBLE

            row.setOnClickListener { abrirFicheiro(context, ficheiro) }

            val params = if (duasColunas) {
                GridLayout.LayoutParams(
                    GridLayout.spec(GridLayout.UNDEFINED, GridLayout.FILL, 1f),
                    GridLayout.spec(GridLayout.UNDEFINED, GridLayout.FILL, 1f)
                ).also {
                    it.width = 0
                    it.height = GridLayout.LayoutParams.WRAP_CONTENT
                    val margem = (density * 5).toInt()
                    it.setMargins(margem, margem, margem, margem)
                }
            } else {
                GridLayout.LayoutParams(
                    GridLayout.spec(GridLayout.UNDEFINED, 1f),
                    GridLayout.spec(GridLayout.UNDEFINED)
                ).also {
                    it.width = GridLayout.LayoutParams.MATCH_PARENT
                    it.height = GridLayout.LayoutParams.WRAP_CONTENT
                    val margem = (density * 4).toInt()
                    it.setMargins(0, margem, 0, margem)
                }
            }
            grid.addView(row, params)
        }
    }

    /** Emoji por extensão do ficheiro. */
    private fun emojiParaFicheiro(nome: String): String =
        FileCategory.classify(nome)?.emoji ?: "📄"

    /** Tamanho legível (B/KB/MB/GB); "" se desconhecido. */
    private fun tamanhoLegivel(bytes: Long): String {
        if (bytes < 0) return ""
        return when {
            bytes < 1024 -> "$bytes B"
            bytes < 1024 * 1024 -> String.format(java.util.Locale.US, "%.1f KB", bytes / 1024f)
            bytes < 1024L * 1024 * 1024 -> String.format(java.util.Locale.US, "%.1f MB", bytes / (1024f * 1024))
            else -> String.format(java.util.Locale.US, "%.2f GB", bytes / (1024f * 1024 * 1024))
        }
    }

    /** Abre o ficheiro no browser/visionador (ACTION_VIEW) — sem crash se não houver app. */
    private fun abrirFicheiro(context: android.content.Context, ficheiro: MediaFileItem) {
        if (ficheiro.uri.isBlank()) {
            Toast.makeText(context, context.getString(R.string.services_url_indisponivel), Toast.LENGTH_SHORT).show()
            return
        }
        try {
            val intent = Intent(Intent.ACTION_VIEW)
            if (ficheiro.uri.startsWith("content://")) {
                intent.setDataAndType(android.net.Uri.parse(ficheiro.uri), tipoMime(ficheiro.name))
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } else {
                intent.data = android.net.Uri.parse(ficheiro.uri)
            }
            context.startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(context, R.string.services_sem_browser, Toast.LENGTH_SHORT).show()
        }
    }

    private fun tipoMime(nome: String): String =
        android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(
            nome.substringAfterLast('.', "").lowercase()
        ) ?: "application/octet-stream"
}
