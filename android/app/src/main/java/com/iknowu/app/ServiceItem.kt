package com.iknowu.app

/**
 * Modelo de um atalho de serviço.
 *
 * @param id identificador único do serviço
 * @param nome nome apresentado no card
 * @param url endereço aberto no browser (configurável em [ServiceCatalog])
 * @param descricao descrição curta opcional apresentada no card
 * @param estado estado opcional (ex.: "Online", "Offline"); nulo/esvazio = sem estado
 * @param estadoOk true se o estado é positivo (ponto verde); false = ponto roxo/aviso
 */
data class ServiceItem(
    val id: String,
    val nome: String,
    val url: String,
    val descricao: String = "",
    val estado: String? = null,
    val estadoOk: Boolean = true
)
