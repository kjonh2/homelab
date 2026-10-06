package com.iknowu.app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.iknowu.app.databinding.FragmentPrinterControlBinding

/**
 * Controlo da impressora 3D Geeetech i3 Pro W.
 *
 * UI autónoma (sem tocar em MainActivity nem nos ficheiros de outros agentes):
 * mostra estado (idle/printing/paused), temperaturas hotbed/bico, progresso
 * da impressão e botões Iniciar/Pausar/Parar. Comunica via HTTP com o
 * servidor local do homelab (OctoPrint/Klipper-style) através de [PrinterApi].
 *
 * Como usar (a partir de qualquer contentor de fragmentos, ex. num diálogo
 * ou navegação existente):
 *   supportFragmentManager.beginTransaction()
 *       .replace(R.id.<container>, PrinterControlFragment())
 *       .addToBackStack(null)
 *       .commit()
 */
class PrinterControlFragment : Fragment() {

    private var _binding: FragmentPrinterControlBinding? = null
    private val binding get() = _binding!!

    private var api: PrinterApi = HttpPrinterApi()

    /** Polling automático do estado/temperaturas/progresso enquanto visível. */
    private val pollHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private var pollRunning = false
    private val pollRunnable = object : Runnable {
        override fun run() {
            if (!pollRunning) return
            refreshState()
            pollHandler.postDelayed(this, POLL_INTERVAL_MS)
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentPrinterControlBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        binding.btnPrinterStart.setOnClickListener {
            confirmCommand("Iniciar impressão?") { api.startPrint { onCommand(it, "Impressão iniciada") } }
        }
        binding.btnPrinterPause.setOnClickListener {
            confirmCommand("Pausar impressão?") { api.pausePrint { onCommand(it, "Impressão pausada") } }
        }
        binding.btnPrinterStop.setOnClickListener {
            confirmCommand("Parar e cancelar a impressão?") { api.stopPrint { onCommand(it, "Impressão parada") } }
        }
        binding.btnPrinterRefresh.setOnClickListener { refreshState() }

        // Aplicar configuração do servidor antes do primeiro refrescamento.
        applyServerConfig()
        refreshState()
    }

    override fun onResume() {
        super.onResume()
        startPolling()
    }

    override fun onPause() {
        stopPolling()
        super.onPause()
    }

    override fun onDestroyView() {
        stopPolling()
        _binding = null
        super.onDestroyView()
    }

    // ------------------------------------------------------------ comandos UI

    private fun confirmCommand(message: String, action: () -> Unit) {
        com.google.android.material.dialog.MaterialAlertDialogBuilder(requireContext())
            .setTitle("Confirmar")
            .setMessage(message)
            .setPositiveButton("Sim") { _, _ -> action() }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun onCommand(result: Result<PrinterApi.CommandResult>, successMsg: String) {
        result
            .onSuccess {
                if (view == null) return
                Toast.makeText(requireContext(), successMsg, Toast.LENGTH_SHORT).show()
                refreshState()
            }
            .onFailure { e ->
                if (view == null) return
                showError("Falha no comando: ${e.message ?: "erro desconhecido"}")
            }
    }

    private fun applyServerConfig() {
        val ep = PrinterEndpoints()
        val url = binding.inputPrinterBaseUrl.text?.toString()?.trim().orEmpty()
        if (url.isNotBlank()) ep.baseUrl = url
        ep.apiKey = binding.inputPrinterApiKey.text?.toString()?.trim()?.takeIf { it.isNotBlank() }
        // Mantém os paths por omissão (OctoPrint-style); alteráveis aqui para Klipper.
        api = HttpPrinterApi(ep)
        binding.inputPrinterBaseUrl.setText(ep.baseUrl)
    }

    // ---------------------------------------------------------- refresh state

    private fun refreshState() {
        if (view == null) return
        binding.textPrinterError.visibility = View.GONE

        api.getStatus { result ->
            if (view == null) return@getStatus
            result
                .onSuccess { s ->
                    if (view == null) return@onSuccess
                    binding.textPrinterState.text = prettyState(s.state, s.printing, s.paused)
                    binding.textPrinterState.setTextColor(stateColor(s.printing, s.paused))
                    binding.btnPrinterPause.text = if (s.paused) "Retomar" else "Pausar"
                }
                .onFailure { e ->
                    if (view == null) return@onFailure
                    showError("Sem resposta do servidor: ${e.message ?: "erro desconhecido"}")
                    binding.textPrinterState.text = "Erro de ligação"
                    binding.textPrinterState.setTextColor(0xFFFF8AA8.toInt())
                }
        }

        api.getTemps { result ->
            if (view == null) return@getTemps
            result.onSuccess { t ->
                if (view == null) return@onSuccess
                binding.textPrinterBed.text = formatTemp(t.bedCurrent, t.bedTarget)
                binding.textPrinterNozzle.text = formatTemp(t.nozzleCurrent, t.nozzleTarget)
            }
        }

        api.getProgress { result ->
            if (view == null) return@getProgress
            result.onSuccess { p ->
                if (view == null) return@onSuccess
                binding.progressPrinter.progress = p.percent
                binding.textPrinterProgress.text =
                    if (p.percent > 0) "$p% concluído" else "0% — sem dados"
                binding.textPrinterJob.text = p.fileName ?: "Sem trabalho"
            }
        }
    }

    private fun prettyState(state: String, printing: Boolean, paused: Boolean): String =
        when {
            paused -> "Em pausa"
            printing -> "A imprimir"
            state.contains("cancel", ignoreCase = true) -> "Cancelado"
            state.contains("error", ignoreCase = true) -> "Erro"
            else -> "Inactivo"
        }

    private fun stateColor(printing: Boolean, paused: Boolean): Int = when {
        printing -> 0xFF9C6BFF.toInt()
        paused -> 0xFFFFC86B.toInt()
        else -> 0xFFE6E1F5.toInt()
    }

    private fun formatTemp(current: Double, target: Double): String {
        val cur = if (current.isNaN()) "--" else current.toInt().toString()
        val tgt = if (target.isNaN()) "--" else target.toInt().toString()
        return "$cur / $tgt °C"
    }

    private fun showError(msg: String) {
        binding.textPrinterError.text = msg
        binding.textPrinterError.visibility = View.VISIBLE
    }

    // ---------------------------------------------------------------- polling

    private fun startPolling() {
        if (pollRunning) return
        pollRunning = true
        pollHandler.postDelayed(pollRunnable, POLL_INTERVAL_MS)
    }

    private fun stopPolling() {
        pollRunning = false
        pollHandler.removeCallbacks(pollRunnable)
    }

    companion object {
        private const val POLL_INTERVAL_MS = 3000L
    }
}
