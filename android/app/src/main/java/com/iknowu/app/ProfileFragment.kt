package com.iknowu.app

import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.google.firebase.auth.FirebaseAuth
import com.iknowu.app.databinding.FragmentProfileBinding
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Perfil do utilizador Firebase + logout + notificações do homelab.
 *
 * Autónomo: pode ser adicionado a qualquer Activity/holder com
 * supportFragmentManager.beginTransaction().replace(id, ProfileFragment()).commit()
 */
class ProfileFragment : Fragment() {

    private var _binding: FragmentProfileBinding? = null
    private val binding get() = _binding!!
    private lateinit var auth: FirebaseAuth
    private lateinit var notif: NotificationsHelper.NotificationManager

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentProfileBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        auth = FirebaseAuth.getInstance()
        notif = NotificationsHelper.get(requireContext()).manager

        bindUser()
        styleAvatar()
        renderNotifications()

        binding.btnLogout.setOnClickListener { logout() }
    }

    // ---- Perfil (FirebaseAuth.currentUser) ----

    private fun bindUser() {
        val user = auth.currentUser
        if (user == null) {
            binding.profileName.text = "Sessão não iniciada"
            binding.profileEmail.text = "—"
            return
        }
        binding.profileName.text = user.displayName ?: user.email?.substringBefore("@") ?: "Utilizador"
        binding.profileEmail.text = user.email ?: user.phoneNumber ?: "Sem email associado"

        val source = (user.displayName ?: user.email ?: "?").trim()
        val initials = source.split(Regex("[@.\\s_-]+"))
            .filter { it.isNotBlank() }
            .take(2)
            .map { it.first().uppercaseChar() }
            .joinToString("")
        binding.avatarInitials.text = initials.ifEmpty { "?" }
    }

    /** Fundo circular roxo para as iniciais (definido em código, sem novo drawable). */
    private fun styleAvatar() {
        val d = GradientDrawable()
        d.shape = GradientDrawable.OVAL
        d.setColor(Color.parseColor("#5E35B1"))
        binding.avatarInitials.background = d
    }

    // ---- Notificações do homelab ----

    private fun renderNotifications() {
        binding.notificationsList.removeAllViews()
        val items = notif.getAll()
        binding.notificationsEmpty.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
        items.forEach { addNotificationRow(it) }
    }

    private fun addNotificationRow(item: NotificationsHelper.Item) {
        val ctx = requireContext()
        val row = LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#1E1930"))
                cornerRadius = dp(10).toFloat()
            }
        }

        val dot = TextView(ctx).apply {
            text = "●"
            setTextColor(if (item.urgent) Color.parseColor("#FF5370") else Color.parseColor("#7C4DFF"))
            setPadding(0, 0, dp(10), 0)
            textSize = 14f
        }

        val col = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        col.addView(TextView(ctx).apply {
            text = item.title
            setTextColor(Color.parseColor("#F2EFFF"))
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
        })
        col.addView(TextView(ctx).apply {
            text = item.message
            setTextColor(Color.parseColor("#A797D9"))
            textSize = 13f
        })
        col.addView(TextView(ctx).apply {
            text = formatDate(item.at)
            setTextColor(Color.parseColor("#6E5FA0"))
            textSize = 11f
            setPadding(0, dp(2), 0, 0)
        })

        row.addView(dot)
        row.addView(col, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val params = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = dp(6) }

        binding.notificationsList.addView(row, params)
    }

    private fun formatDate(at: Long): String =
        SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault()).format(Date(at))

    // ---- Logout ----

    private fun logout() {
        auth.signOut()
        val intent = Intent(requireContext(), LoginActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        startActivity(intent)
    }

    private fun dp(v: Int): Int = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics
    ).toInt()

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
