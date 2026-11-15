package com.iknowu.app

import java.net.ConnectException
import java.net.UnknownHostException
import org.junit.Assert.assertTrue
import org.junit.Test

class DrisaConnectionErrorTest {
    @Test
    fun unknownMagicDnsHostPointsToTailscale() {
        val message = DrisaConnectionError.userMessage(UnknownHostException("private host"))

        assertTrue(message.contains("Tailscale"))
        assertTrue(message.contains("endereço privado"))
    }

    @Test
    fun unreachablePrivateRoutePointsToTailscale() {
        val message = DrisaConnectionError.userMessage(ConnectException("unreachable"))

        assertTrue(message.contains("rede privada"))
        assertTrue(message.contains("Tailscale"))
    }

    @Test
    fun gatewayHttpFailureDoesNotExposeExceptionDetails() {
        val message = DrisaConnectionError.userMessage(UnknownHostException("private host"), httpCode = 403)

        assertTrue(message.contains("HTTP 403"))
        assertTrue(message.contains("token"))
        assertTrue(!message.contains("private host"))
    }
}
