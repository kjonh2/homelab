package com.iknowu.app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.iknowu.app.databinding.FragmentCameraPreviewBinding

/**
 * Câmaras do homelab — preview em vídeo das 2 câmaras USB do PC
 * dentro do IKnowU, via streams MJPEG (mjpeg-streamer/Motion/ffmpeg).
 *
 * Ficheiro autónomo (prefixo Camera*): não toca em MainActivity nem
 * nos ficheiros de outros agentes. Reutiliza [CameraStreamView].
 *
 * Como usar:
 *   supportFragmentManager.beginTransaction()
 *       .replace(R.id.<container>, CameraPreviewFragment())
 *       .addToBackStack(null)
 *       .commit()
 */
class CameraPreviewFragment : Fragment() {

    private var _binding: FragmentCameraPreviewBinding? = null
    private val binding get() = _binding!!

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentCameraPreviewBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        binding.btnCamerasStart.setOnClickListener {
            val url1 = binding.inputCameraUrl1.text?.toString()?.trim().orEmpty()
            val url2 = binding.inputCameraUrl2.text?.toString()?.trim().orEmpty()
            if (url1.isBlank() && url2.isBlank()) {
                Toast.makeText(
                    requireContext(),
                    "Introduz pelo menos um URL de câmara (MJPEG).",
                    Toast.LENGTH_SHORT
                ).show()
                return@setOnClickListener
            }
            if (url1.isNotBlank()) binding.cameraView1.start(url1)
            if (url2.isNotBlank()) binding.cameraView2.start(url2)
            Toast.makeText(requireContext(), "A ligar às câmaras...", Toast.LENGTH_SHORT).show()
        }

        binding.btnCamerasStop.setOnClickListener {
            binding.cameraView1.stop()
            binding.cameraView2.stop()
            Toast.makeText(requireContext(), "Câmaras desligadas.", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onPause() {
        // Evita ligações abertas fora de ecrã; retoma ao voltar.
        val url1 = binding.inputCameraUrl1.text?.toString()?.trim().orEmpty()
        val url2 = binding.inputCameraUrl2.text?.toString()?.trim().orEmpty()
        binding.cameraView1.stop()
        binding.cameraView2.stop()
        pendingUrl1 = url1
        pendingUrl2 = url2
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        if (pendingUrl1.isNotBlank()) binding.cameraView1.start(pendingUrl1)
        if (pendingUrl2.isNotBlank()) binding.cameraView2.start(pendingUrl2)
        pendingUrl1 = ""
        pendingUrl2 = ""
    }

    override fun onDestroyView() {
        binding.cameraView1.stop()
        binding.cameraView2.stop()
        _binding = null
        super.onDestroyView()
    }

    private var pendingUrl1: String = ""
    private var pendingUrl2: String = ""

    companion object {
        /** URLs predefinidos sugeridos para as câmaras do homelab (editáveis na UI). */
        const val DEFAULT_URL_CAM_1 = "http://[IP_ADDRESS]:8081/?action=stream"
        const val DEFAULT_URL_CAM_2 = "http://[IP_ADDRESS]:8082/?action=stream"
    }
}
