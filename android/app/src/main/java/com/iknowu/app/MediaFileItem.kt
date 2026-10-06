package com.iknowu.app

/**
 * Modelo de um ficheiro (local ou de share do homelab).
 *
 * @param name nome apresentado (com extensão)
 * @param sizeBytes tamanho em bytes (-1 se desconhecido, ex.: shares remotos)
 * @param uri URI para abrir o ficheiro (local: content:// do MediaStore; remoto: http(s)://)
 * @param isRemote true se veio de um share do homelab
 */
data class MediaFileItem(
    val name: String,
    val sizeBytes: Long = -1L,
    val uri: String = "",
    val isRemote: Boolean = false
)
