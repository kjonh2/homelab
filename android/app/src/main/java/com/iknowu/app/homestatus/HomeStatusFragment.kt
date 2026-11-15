package com.iknowu.app.homestatus

import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.iknowu.app.R
import java.text.DateFormat
import java.util.Date

/** Shows the authenticated health state of services running on the Iku VPS. */
class HomeStatusFragment : Fragment() {

    private var _binding: com.iknowu.app.databinding.FragmentHomeStatusBinding? = null
    private val binding get() = _binding!!
    private lateinit var api: HomeStatusApi
    private var loading = false
    private val handler = Handler(Looper.getMainLooper())
    private val poller = object : Runnable {
        override fun run() {
            refresh()
            handler.postDelayed(this, HomeStatusApi.POLL_INTERVAL_MS)
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View {
        _binding = com.iknowu.app.databinding.FragmentHomeStatusBinding.inflate(inflater, container, false)
        api = HomeStatusApi(requireContext())
        return binding.root
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
        handler.removeCallbacks(poller)
        api.cancelAll()
        loading = false
        _binding = null
        super.onDestroyView()
    }

    private fun refresh() {
        if (_binding == null || loading) return
        loading = true
        binding.homeStatusUpdated.text = getString(R.string.home_status_updating)
        binding.homeStatusError.text = ""
        api.fetchSnapshot { snapshot, error ->
            loading = false
            if (_binding == null) return@fetchSnapshot
            if (snapshot == null) {
                binding.homeStatusUpdated.text = getString(R.string.home_status_offline)
                binding.homeStatusError.text = error.orEmpty()
                binding.homeStatusSummary.text = getString(R.string.home_status_unavailable)
                binding.homeStatusServices.removeAllViews()
                return@fetchSnapshot
            }
            render(snapshot)
        }
    }

    private fun render(snapshot: HomeStatusApi.HomeSnapshot) {
        binding.homeStatusUpdated.text = getString(
            R.string.home_status_updated_at,
            DateFormat.getTimeInstance(DateFormat.SHORT).format(Date()),
        )
        binding.homeStatusSummary.text = getString(
            R.string.home_status_services_count,
            snapshot.servicesUp,
            snapshot.services.size,
        )
        binding.homeStatusServices.removeAllViews()
        if (snapshot.services.isEmpty()) {
            binding.homeStatusServices.addView(serviceLabel(getString(R.string.home_status_no_services), "#9C9CC0"))
            return
        }
        snapshot.services.sortedBy { it.name }.forEach { service ->
            val row = LinearLayout(requireContext()).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(12), dp(10), dp(12), dp(10))
                setBackgroundResource(R.drawable.home_status_metric_bg)
                contentDescription = "${service.name}: ${if (service.up) "disponível" else "sem resposta"}"
            }
            val title = TextView(requireContext()).apply {
                text = "${if (service.up) "●" else "○"}  ${service.name}"
                textSize = 14f
                setTextColor(Color.parseColor(if (service.up) "#4ADE80" else "#F87171"))
            }
            val detail = TextView(requireContext()).apply {
                text = "${service.description} · ${if (service.up) "Disponível" else "Sem resposta"}"
                textSize = 12f
                setTextColor(Color.parseColor("#B8B6CA"))
                setPadding(dp(22), dp(3), 0, 0)
            }
            row.addView(title)
            row.addView(detail)
            binding.homeStatusServices.addView(row, LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = dp(8)
            })
        }
    }

    private fun serviceLabel(text: String, color: String) = TextView(requireContext()).apply {
        this.text = text
        textSize = 12f
        setTextColor(Color.parseColor(color))
        setPadding(dp(4), dp(8), dp(4), dp(8))
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        fun newInstance(): HomeStatusFragment = HomeStatusFragment()
    }
}
