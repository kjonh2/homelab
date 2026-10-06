package com.iknowu.app.homestatus

import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.iknowu.app.R
import java.util.Locale

/**
 * Bloco "Estado do homelab": containers, CPU/RAM, uptime, discos e partilhas
 * de ficheiros (FTP/SMB/NFS), com polling de 10 s sobre a API do Prometheus
 * do homelab (stack docker-compose.homelab.yml, repo kjonh2/homelab).
 *
 * Autónomo: basta adicionar este fragmento a um contentor (ex. MainActivity)
 * via supportFragmentManager. Não modifica nenhum ficheiro partilhado.
 */
class HomeStatusFragment : Fragment() {

    private var _binding: com.iknowu.app.databinding.FragmentHomeStatusBinding? = null
    private val binding get() = _binding!!

    private lateinit var api: HomeStatusApi
    private val handler = Handler(Looper.getMainLooper())
    private val poller = object : Runnable {
        override fun run() {
            refresh()
            handler.postDelayed(this, HomeStatusApi.POLL_INTERVAL_MS)
        }
    }

    /** Catálogo de partilhas — configurável pelo host antes de mostrar o fragmento. */
    var shares: List<HomeStatusApi.HomeStatusShare>
        get() = api.shares
        set(value) { api.setShares(value) }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = com.iknowu.app.databinding.FragmentHomeStatusBinding.inflate(inflater, container, false)
        api = HomeStatusApi()
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        refresh()
    }

    override fun onResume() {
        super.onResume()
        handler.post(poller)
    }

    override fun onPause() {
        handler.removeCallbacks(poller)
        super.onPause()
    }

    override fun onDestroyView() {
        api.cancelAll()
        _binding = null
        super.onDestroyView()
    }

    private fun refresh() {
        _binding ?: return
        binding.homeStatusUpdated.text = getString(R.string.home_status_updating)
        binding.homeStatusError.text = ""
        api.fetchSnapshot { snap, err ->
            _binding ?: return@fetchSnapshot
            if (snap == null) {
                binding.homeStatusError.text = getString(R.string.home_status_error, err ?: "?")
                binding.homeStatusUpdated.text = getString(R.string.home_status_offline)
                return@fetchSnapshot
            }
            render(snap)
        }
        // Sondas de partilhas (TCP) — executadas em paralelo com o snapshot
        renderShareRows()
    }

    private fun render(snap: HomeStatusApi.HomeSnapshot) {
        binding.homeStatusUpdated.text = getString(
            R.string.home_status_updated_at,
            java.text.DateFormat.getTimeInstance(java.text.DateFormat.SHORT).format(java.util.Date())
        )
        binding.homeStatusContainers.text =
            getString(R.string.home_status_containers_value, snap.containersUp, snap.containersTotal)
        binding.homeStatusCpu.text = snap.cpuPercent?.let { fmtPct(it) } ?: "— %"
        binding.homeStatusRam.text = snap.ramPercent?.let { fmtPct(it) } ?: "— %"
        (binding.homeStatusCpuBar as? ProgressBar)?.progress = snap.cpuPercent?.toInt()?.coerceIn(0, 100) ?: 0
        (binding.homeStatusRamBar as? ProgressBar)?.progress = snap.ramPercent?.toInt()?.coerceIn(0, 100) ?: 0
        binding.homeStatusUptime.text = snap.uptimeSeconds?.let { fmtUptime(it) } ?: "—"

        val sb = StringBuilder()
        snap.services.sortedBy { it.name }.forEach { s ->
            sb.append(if (s.up) "● " else "○ ").append(s.name).append('\n')
        }
        if (snap.services.isEmpty()) sb.append(getString(R.string.home_status_no_services))
        binding.homeStatusServices.text = sb.toString().trimEnd()

        renderDisks(snap.disks)
    }

    // ------------------------------------------------------------------ discos

    private fun renderDisks(disks: List<HomeStatusApi.DiskUsage>) {
        val container = binding.homeStatusDisksList
        container.removeAllViews()
        if (disks.isEmpty()) {
            container.addView(newLabel(getString(R.string.home_status_no_disks), "#9C9CC0"))
            return
        }
        for (d in disks) {
            container.addView(buildDiskRow(d))
        }
    }

    private fun buildDiskRow(d: HomeStatusApi.DiskUsage): View {
        val ctx = binding.root.context
        val row = LinearLayout(ctx)
        row.orientation = LinearLayout.VERTICAL
        row.setPadding(0, dp(8), 0, dp(4))

        val alert = d.isCritical
        val accent = if (alert) "#F87171" else "#A78BFA"

        val title = TextView(ctx)
        title.text = getString(
            R.string.home_status_disk_line,
            d.device.ifBlank { d.mount },
            fmtPct(d.usedPercent),
            fmtBytes(d.usedBytes),
            fmtBytes(d.totalBytes)
        )
        title.setTextColor(Color.parseColor(if (alert) "#F87171" else "#E5E7EB"))
        title.textSize = 13f
        row.addView(title)

        val bar = ProgressBar(ctx, null, android.R.attr.progressBarStyleHorizontal)
        bar.max = 100
        bar.progress = d.usedPercent.toInt().coerceIn(0, 100)
        bar.progressTintList = android.content.res.ColorStateList.valueOf(Color.parseColor(accent))
        row.addView(bar, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ).also { it.topMargin = dp(4) })

        if (alert) {
            val warn = TextView(ctx)
            warn.text = getString(R.string.home_status_disk_alert, d.mount)
            warn.setTextColor(Color.parseColor("#F87171"))
            warn.textSize = 11f
            row.addView(warn)
        }
        return row
    }

    // ---------------------------------------------------------------- partilhas

    private fun renderShareRows() {
        val container = binding.homeStatusSharesList
        container.removeAllViews()
        val list = api.shares
        if (list.isEmpty()) {
            container.addView(newLabel(getString(R.string.home_status_no_shares), "#9C9CC0"))
            return
        }
        for (share in list) {
            container.addView(buildShareRow(share))
        }
    }

    private fun buildShareRow(share: HomeStatusApi.HomeStatusShare): View {
        val ctx = binding.root.context
        val row = LinearLayout(ctx)
        row.orientation = LinearLayout.HORIZONTAL
        row.setPadding(0, dp(6), 0, dp(6))
        row.gravity = android.view.Gravity.CENTER_VERTICAL

        val texts = LinearLayout(ctx)
        texts.orientation = LinearLayout.VERTICAL
        texts.layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)

        val name = TextView(ctx)
        name.text = share.name
        name.setTextColor(Color.parseColor("#E5E7EB"))
        name.textSize = 13f
        texts.addView(name)

        val url = TextView(ctx)
        url.text = share.url
        url.setTextColor(Color.parseColor("#9C9CC0"))
        url.textSize = 11f
        url.typeface = android.graphics.Typeface.MONOSPACE
        texts.addView(url)

        val state = TextView(ctx)
        state.text = getString(R.string.home_status_share_probing)
        state.setTextColor(Color.parseColor("#9C9CC0"))
        state.textSize = 11f
        texts.addView(state)

        row.addView(texts)

        val open = Button(ctx)
        open.text = getString(R.string.home_status_share_open)
        open.textSize = 11f
        open.setAllCaps(false)
        open.setTextColor(Color.WHITE)
        open.backgroundTintList = android.content.res.ColorStateList.valueOf(Color.parseColor("#7C3AED"))
        open.minWidth = 0
        open.minimumWidth = 0
        row.addView(open)

        open.setOnClickListener { openShare(share) }

        api.probeShare(share) { online ->
            if (_binding == null) return@probeShare
            state.text = if (online) getString(R.string.home_status_share_online)
                         else getString(R.string.home_status_share_offline)
            state.setTextColor(Color.parseColor(if (online) "#4ADE80" else "#F87171"))
        }
        return row
    }

    /** Abre a partilha no gestor de ficheiros / browser via URI ftp:// ou smb://. */
    private fun openShare(share: HomeStatusApi.HomeStatusShare) {
        val uri = Uri.parse(share.url)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            data = uri
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            // Alguns gestores só registam um dos esquemas — tenta o outro esquema comum
            val altScheme = when (uri.scheme?.lowercase(Locale.ROOT)) {
                "ftp" -> "smb"; "smb" -> "ftp"; "nfs" -> "smb"; else -> null
            }
            var handled = false
            if (altScheme != null) {
                try {
                    val alt = Uri.Builder().scheme(altScheme)
                        .encodedAuthority(uri.encodedAuthority).build()
                    startActivity(Intent(Intent.ACTION_VIEW, alt).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    handled = true
                } catch (_: Exception) { /* sem app para o esquema alternativo */ }
            }
            if (!handled) {
                // Última alternativa: copiar o endereço e informar
                val cm = requireContext().getSystemService(android.content.Context.CLIPBOARD_SERVICE)
                        as android.content.ClipboardManager
                cm.setPrimaryClip(android.content.ClipData.newPlainText("share", share.url))
                Toast.makeText(context, getString(R.string.home_status_share_no_app), Toast.LENGTH_LONG).show()
            }
        }
    }

    // ------------------------------------------------------------------ utils

    private fun newLabel(text: String, colorHex: String): TextView {
        val t = TextView(requireContext())
        t.text = text
        t.setTextColor(Color.parseColor(colorHex))
        t.textSize = 12f
        return t
    }

    private fun fmtPct(v: Double): String = String.format(Locale("pt", "PT"), "%.1f %%", v)

    private fun fmtBytes(bytes: Double): String {
        val units = arrayOf("B", "KB", "MB", "GB", "TB")
        var v = bytes
        var u = 0
        while (v >= 1024 && u < units.size - 1) { v /= 1024; u++ }
        return String.format(Locale("pt", "PT"), "%.1f %s", v, units[u])
    }

    private fun fmtUptime(sec: Double): String {
        val d = sec.toLong() / 86400
        val h = (sec.toLong() % 86400) / 3600
        return getString(R.string.home_status_uptime_value, d, h)
    }

    private fun dp(v: Int): Int =
        (v * resources.displayMetrics.density).toInt()

    companion object {
        fun newInstance(): HomeStatusFragment = HomeStatusFragment()
    }
}
