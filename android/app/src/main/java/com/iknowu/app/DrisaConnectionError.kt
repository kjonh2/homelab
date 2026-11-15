package com.iknowu.app

import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

internal object DrisaConnectionError {
    fun userMessage(error: Throwable, httpCode: Int? = null): String {
        if (httpCode != null) {
            return "A gateway Drisa recusou a ligação (HTTP $httpCode). Verifica o identificador e o token do dispositivo."
        }

        val causes = generateSequence(error) { it.cause }.toList()
        return when {
            causes.any { it is UnknownHostException } ->
                "Não foi possível encontrar o endereço privado da Drisa. Liga o Tailscale neste telemóvel e tenta novamente."
            causes.any { it is ConnectException || it is NoRouteToHostException || it is SocketTimeoutException } ->
                "A rede privada da Drisa está inacessível. Confirma que o Tailscale está ligado no telemóvel e tenta novamente."
            else -> "Falha de rede ao ligar à Drisa. Confirma o Tailscale e tenta novamente."
        }
    }
}
