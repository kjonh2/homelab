package com.iknowu.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.InputType
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.iknowu.app.databinding.FragmentFilesCategoriesBinding
import java.util.concurrent.Executors

/**
 * Secção "Ficheiros por categoria": grelha de 7 tiles (📷 Fotos, 🎬 Vídeo,
 * 🎵 Áudio, 📄 Docs, 🏥 Medical, 💰 Finanças, 🔒 Segurança) com contagem de
 * ficheiros; tocar num tile abre a lista/grelha dos ficheiros dessa categoria.
 *
 * Fontes configuráveis:
 *  - Storage local: MediaStore (ver [MediaFileScanner]); pede permissão de
 *    leitura à 1ª utilização.
 *  - Shares do homelab: URL configurável no topo da secção (ver
 *    [FileShareClient] — aceita JSON ou listagem HTML de directório).
 *
 * Medical e Segurança estão protegidos por PIN opcional ([FilePinManager]):
 * na 1ª entrada pergunta se quer definir um PIN (ou "Sem PIN"); a partir daí
 * pede o PIN sempre que abre a categoria.
 *
 * Este fragmento é autónomo — para o usar, adiciona-o a um contentor
 * (ex.: supportFragmentManager). Não toca na MainActivity.
 */
class FilesCategoryFragment : Fragment() {

    private var _binding: FragmentFilesCategoriesBinding? = null
    private val binding get() = _binding!!

    private val executor = Executors.newSingleThreadExecutor()

    /** Categoria actualmente aberta (vista lista); null = vista grelha de tiles. */
    private var categoriaAberta: FileCategory? = null

    /** Contagens locais já calculadas (exibidas imediatamente nos tiles). */
    private val contagensLocais = HashMap<FileCategory, Int>()

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> refrescarContagens() }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentFilesCategoriesBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        binding.textShareEstado.setOnClickListener { pedirUrlShare() }
        binding.textVoltar.setOnClickListener { mostrarGrelha() }

        mostrarGrelha()
        pedirPermissaoSeNecessario()
        refrescarContagens()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    // ---------------------------------------------------------------------
    // Vista 1 — grelha de tiles
    // ---------------------------------------------------------------------

    private fun mostrarGrelha() {
        categoriaAberta = null
        binding.gridCategorias.visibility = View.VISIBLE
        binding.listaFicheirosContainer.visibility = View.GONE
        actualizarEstadoShare()
        FileTileAdapter.popularTiles(
            binding.gridCategorias,
            contagensLocais.mapValues { it.value },
            onTileClick = { abrirCategoria(it) }
        )
    }

    /** Actualiza a linha de estado do share do homelab. */
    private fun actualizarEstadoShare() {
        binding.textShareEstado.text = if (FileShareClient.isConfigured(requireContext())) {
            getString(R.string.files_share_ok) + " · " + FileShareClient.shareUrl(requireContext())
        } else {
            getString(R.string.files_share_nao_config)
        }
    }

    /** Diálogo para configurar/remover o URL do share do homelab. */
    private fun pedirUrlShare() {
        val context = requireContext()
        val input = EditText(context).apply {
            hint = "http://[IP_ADDRESS]:8080/files"
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            setText(FileShareClient.shareUrl(context))
            val pad = (resources.displayMetrics.density * 20).toInt()
            setPadding(pad, pad / 2, pad, pad / 2)
        }
        val container = FrameLayout(context).apply {
            val pad = (resources.displayMetrics.density * 8).toInt()
            setPadding(pad, 0, pad, 0)
            addView(input)
        }

        AlertDialog.Builder(context)
            .setTitle(getString(R.string.files_share_url_titulo))
            .setMessage(getString(R.string.files_share_url_msg))
            .setView(container)
            .setPositiveButton(getString(R.string.files_share_ok_definir)) { _, _ ->
                FileShareClient.setShareUrl(context, input.text.toString())
                actualizarEstadoShare()
                refrescarContagens()
            }
            .setNeutralButton(getString(R.string.files_share_ok_remover)) { _, _ ->
                FileShareClient.setShareUrl(context, "")
                actualizarEstadoShare()
                refrescarContagens()
            }
            .setNegativeButton(getString(R.string.files_share_cancelar), null)
            .show()
    }

    /** Actualiza as contagens dos tiles (local + share) em thread de fundo. */
    private fun refrescarContagens() {
        val context = requireContext() ?: return
        executor.execute {
            val contagens = HashMap<FileCategory, Int>()
            FileCategory.ALL.forEach { cat ->
                val ficheiros = MediaFileScanner.scan(context, cat)
                contagens[cat] = ficheiros.size
            }
            // Shares do homelab (se configurados) — somam-se às contagens locais
            val remotas = FileShareClient.countAll(context)
            remotas.forEach { (cat, n) -> contagens[cat] = (contagens[cat] ?: 0) + n }

            contagensLocais.clear()
            contagensLocais.putAll(contagens)

            if (_binding == null) return@execute
            binding.root.post {
                if (_binding == null) return@post
                if (categoriaAberta == null) {
                    FileTileAdapter.popularTiles(
                        binding.gridCategorias, contagens, onTileClick = { abrirCategoria(it) }
                    )
                }
            }
        }
    }

    // ---------------------------------------------------------------------
    // Acesso às categorias (com PIN opcional)
    // ---------------------------------------------------------------------

    private fun abrirCategoria(categoria: FileCategory) {
        if (categoria.needsPin) {
            pedirPinOuDefinir(categoria)
        } else {
            mostrarFicheiros(categoria)
        }
    }

    /** PIN de [categoria]: se ainda não decidido, pergunta se quer definir; senão pede o PIN. */
    private fun pedirPinOuDefinir(categoria: FileCategory) {
        val context = requireContext()
        when {
            !FilePinManager.hasDecided(context) ->
                AlertDialog.Builder(context)
                    .setTitle(getString(R.string.files_pin_definir_titulo))
                    .setMessage(getString(R.string.files_pin_definir_msg))
                    .setPositiveButton(getString(R.string.files_pin_definir_botao)) { _, _ ->
                        dialogoDefinirPin(context) {
                            mostrarFicheiros(categoria)
                        }
                    }
                    .setNeutralButton(getString(R.string.files_pin_sem_botao)) { _, _ ->
                        FilePinManager.chooseNoPin(context)
                        mostrarFicheiros(categoria)
                    }
                    .setNegativeButton(getString(R.string.files_share_cancelar), null)
                    .show()

            FilePinManager.hasPin(context) -> dialogoPedirPin(context) {
                mostrarFicheiros(categoria)
            }

            else -> mostrarFicheiros(categoria) // escolheu "Sem PIN" na 1ª entrada
        }
    }

    private fun dialogoDefinirPin(context: android.content.Context, onSuccess: () -> Unit) {
        val input = criarInputPin(context)
        AlertDialog.Builder(context)
            .setTitle(getString(R.string.files_pin_definir_titulo))
            .setView(criarContainerInput(context, input))
            .setPositiveButton(getString(R.string.files_pin_definir_botao)) { _, _ ->
                val pin = input.text.toString()
                if (pinValido(pin)) {
                    FilePinManager.setPin(context, pin)
                    onSuccess()
                } else {
                    Toast.makeText(context, R.string.files_pin_invalido, Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton(getString(R.string.files_share_cancelar), null)
            .show()
    }

    private fun dialogoPedirPin(context: android.content.Context, onSuccess: () -> Unit) {
        val input = criarInputPin(context)
        val dialog = AlertDialog.Builder(context)
            .setTitle(getString(R.string.files_pin_pedir_titulo))
            .setView(criarContainerInput(context, input))
            .setPositiveButton(getString(R.string.files_pin_pedir_ok), null)
            .setNegativeButton(getString(R.string.files_share_cancelar), null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                if (FilePinManager.verifyPin(context, input.text.toString())) {
                    dialog.dismiss()
                    onSuccess()
                } else {
                    Toast.makeText(context, R.string.files_pin_errado, Toast.LENGTH_SHORT).show()
                    input.text.clear()
                }
            }
        }
        dialog.show()
    }

    private fun criarInputPin(context: android.content.Context): EditText =
        EditText(context).apply {
            hint = getString(R.string.files_pin_hint)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
        }

    private fun criarContainerInput(context: android.content.Context, input: EditText): FrameLayout =
        FrameLayout(context).apply {
            val pad = (resources.displayMetrics.density * 20).toInt()
            setPadding(pad, (pad / 4), pad, 0)
            addView(input)
        }

    private fun pinValido(pin: String): Boolean = pin.length in 4..8 && pin.all { it.isDigit() }

    // ---------------------------------------------------------------------
    // Vista 2 — lista/grelha de ficheiros de uma categoria
    // ---------------------------------------------------------------------

    private fun mostrarFicheiros(categoria: FileCategory) {
        val context = context ?: return
        categoriaAberta = categoria
        binding.gridCategorias.visibility = View.GONE
        binding.listaFicheirosContainer.visibility = View.VISIBLE
        binding.textCategoriaTitulo.text = "${categoria.emoji} ${categoria.label}"
        binding.progressFicheiros.visibility = View.VISIBLE
        binding.textVazio.visibility = View.GONE
        binding.gridFicheiros.removeAllViews()

        executor.execute {
            val locais = MediaFileScanner.scan(context, categoria)
            val remotos = try {
                FileShareClient.listFiles(context, categoria)
            } catch (_: Exception) {
                emptyList()
            }
            val ficheiros = locais + remotos

            if (_binding == null || categoriaAberta != categoria) return@execute
            binding.root.post {
                if (_binding == null || categoriaAberta != categoria) return@post
                binding.progressFicheiros.visibility = View.GONE
                if (ficheiros.isEmpty()) {
                    binding.textVazio.visibility = View.VISIBLE
                } else {
                    FileTileAdapter.popularFicheiros(
                        binding.gridFicheiros, ficheiros, duasColunas = catGrelha(categoria)
                    )
                }
            }
        }
    }

    /** Fotos/Vídeo/Áudio em grelha 2 colunas; resto em lista. */
    private fun catGrelha(categoria: FileCategory): Boolean = categoria in
        setOf(FileCategory.FOTOS, FileCategory.VIDEO, FileCategory.AUDIO)

    private fun pedirPermissaoSeNecessario() {
        val context = context ?: return
        if (MediaFileScanner.hasStoragePermission(context)) return
        if (ContextCompat.checkSelfPermission(
                context, Manifest.permission.READ_EXTERNAL_STORAGE
            ) == PackageManager.PERMISSION_GRANTED
        ) return
        Toast.makeText(context, R.string.files_perm_necessaria, Toast.LENGTH_LONG).show()
        permLauncher.launch(Manifest.permission.READ_EXTERNAL_STORAGE)
    }
}
