package com.iknowu.app

import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.GridLayout
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.iknowu.app.databinding.FragmentServicesShortcutsBinding
import com.iknowu.app.databinding.ServiceCardShortcutBinding

/**
 * Bloco "Atalhos de serviços": grelha de cards (dark/purple) com atalhos
 * para Hermes, Grafana, N8N, OpenClaw, OpenCode, Antigravity e MCPs.
 *
 * Os cards são gerados a partir de [ServiceCatalog.servicos] — para adicionar
 * um serviço basta acrescentá-lo ao catálogo; o fragmento não precisa de mudar.
 *
 * Este fragmento é autónomo: para o usar, adiciona-o a um contentor
 * (ex.: supportFragmentManager) — não toca na MainActivity.
 */
class ServicesShortcutFragment : Fragment() {

    private var _binding: FragmentServicesShortcutsBinding? = null
    private val binding get() = _binding!!

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentServicesShortcutsBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        popularGrelha()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    /** Constrói um card por serviço do catálogo. */
    private fun popularGrelha() {
        val grid = binding.gridServicos
        grid.removeAllViews()

        ServiceCatalog.servicos.forEach { servico ->
            val cardBinding = ServiceCardShortcutBinding.inflate(layoutInflater, grid, false)
            val card = cardBinding.root as FrameLayout

            // Ícone (com fallback genérico)
            val iconRes = iconeParaServico(servico.id)
            cardBinding.icServico.setImageResource(iconRes)

            // Nome e descrição
            cardBinding.nomeServico.text = servico.nome
            if (servico.descricao.isNotBlank()) {
                cardBinding.descServico.text = servico.descricao
                cardBinding.descServico.visibility = View.VISIBLE
            }

            // Estado opcional (ponto verde/laranja + texto); esconde se não existir
            val estado = servico.estado
            if (estado.isNullOrBlank()) {
                cardBinding.estadoLinha.visibility = View.GONE
            } else {
                cardBinding.estadoTexto.text = estado
                val corDot = if (servico.estadoOk) {
                    ContextCompat.getColor(requireContext(), android.R.color.holo_green_light)
                } else {
                    Color.parseColor("#FFA500")
                }
                cardBinding.estadoDot.background?.setTint(corDot)
            }

            // Abrir o URL no browser
            card.setOnClickListener { abrirServico(servico) }

            // Linha/coluna na grelha (2 colunas com peso igual)
            val params = GridLayout.LayoutParams(
                GridLayout.spec(GridLayout.UNDEFINED, GridLayout.FILL, 1f),
                GridLayout.spec(GridLayout.UNDEFINED, GridLayout.FILL, 1f)
            )
            params.width = 0
            params.height = GridLayout.LayoutParams.WRAP_CONTENT
            val margem = (resources.displayMetrics.density * 8).toInt()
            params.setMargins(margem, margem, margem, margem)
            grid.addView(card, params)
        }
    }

    /** Abre o URL do serviço no browser (ACTION_VIEW). */
    private fun abrirServico(servico: ServiceItem) {
        val url = servico.url
        // Placeholder por preencher (TODO no ServiceCatalog) — avisa em vez de crashar.
        if (url.contains("IP_DO_SERVIDOR") || url.isBlank()) {
            Toast.makeText(requireContext(), R.string.services_url_indisponivel, Toast.LENGTH_SHORT).show()
            return
        }
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(requireContext(), R.string.services_sem_browser, Toast.LENGTH_SHORT).show()
        }
    }

    /** Ícone por serviço; novos serviços sem mapeamento caem no genérico. */
    private fun iconeParaServico(id: String): Int = when (id) {
        "hermes" -> R.drawable.service_icon_hermes
        "grafana" -> R.drawable.service_icon_grafana
        "n8n" -> R.drawable.service_icon_n8n
        else -> R.drawable.service_icon_generic
    }
}
