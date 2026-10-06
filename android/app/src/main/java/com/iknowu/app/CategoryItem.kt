package com.iknowu.app

/**
 * Categorias de ficheiros da secção "Ficheiros".
 *
 * Cada categoria define:
 *  - emoji + nome (PT-PT) apresentados no tile;
 *  - se está protegida por PIN (Medical e Segurança);
 *  - extensões e palavras-chave usadas na classificação automática de ficheiros
 *    (locais via MediaStore e remotos via shares do homelab).
 *
 * A ordem da enumeração é a ordem dos tiles na grelha.
 */
enum class FileCategory(
    val id: String,
    val emoji: String,
    val label: String,
    val needsPin: Boolean,
    val extensions: Set<String>,
    val keywords: Set<String>
) {
    FOTOS(
        id = "fotos", emoji = "📷", label = "Fotos", needsPin = false,
        extensions = setOf("jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "svg"),
        keywords = setOf("foto", "photo", "imagem")
    ),
    VIDEO(
        id = "video", emoji = "🎬", label = "Vídeo", needsPin = false,
        extensions = setOf("mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "m4v", "3gp"),
        keywords = setOf("video", "filme")
    ),
    AUDIO(
        id = "audio", emoji = "🎵", label = "Áudio", needsPin = false,
        extensions = setOf("mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma"),
        keywords = setOf("audio", "musica", "podcast")
    ),
    DOCS(
        id = "docs", emoji = "📄", label = "Docs", needsPin = false,
        extensions = setOf("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "odt", "ods", "odp", "csv", "rtf", "md"),
        keywords = setOf("documento", "doc", "nota")
    ),
    MEDICAL(
        id = "medical", emoji = "🏥", label = "Medical", needsPin = true,
        extensions = setOf("dcm", "hl7", "fhir"),
        keywords = setOf("medical", "medic", "saude", "health", "hospital", "receita", "prescric", "exame", "analise", "clinica", "doutor", "medico", "vacin")
    ),
    FINANCE(
        id = "financas", emoji = "💰", label = "Finanças", needsPin = false,
        extensions = setOf("ofx", "qif", "gnc"),
        keywords = setOf("financ", "fatura", "factura", "recibo", "banco", "bank", "imposto", "irs", "salario", "pagamento", "fatura")
    ),
    SECURITY(
        id = "seguranca", emoji = "🔒", label = "Segurança", needsPin = true,
        extensions = setOf("enc", "key", "pem", "p12", "pfx", "jks", "keystore", "pgp", "gpg", "asc"),
        keywords = setOf("seguranca", "security", "password", "senhas", "vault", "chave", "backup", "cifra", "encript")
    );

    /** true se o nome/valor encaixa nesta categoria (por extensão ou palavra-chave). */
    fun matches(fileName: String): Boolean {
        val lower = fileName.lowercase()
        if (extensions.any { lower.endsWith(".$it") }) return true
        return keywords.any { lower.contains(it) }
    }

    companion object {
        /** Ordem dos tiles na grelha. */
        val ALL: List<FileCategory> = values().toList()

        /** Classifica um nome de ficheiro — seguras (pin) primeiro para evitar colisões. */
        fun classify(fileName: String): FileCategory? =
            ALL.filter { it.needsPin }.firstOrNull { it.matches(fileName) }
                ?: ALL.firstOrNull { it.matches(fileName) }
    }
}
