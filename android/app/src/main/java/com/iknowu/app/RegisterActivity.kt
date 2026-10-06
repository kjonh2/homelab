package com.iknowu.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.iknowu.app.databinding.ActivityRegisterBinding
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.UserProfileChangeRequest

class RegisterActivity : AppCompatActivity() {

    private lateinit var binding: ActivityRegisterBinding
    private lateinit var auth: FirebaseAuth

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityRegisterBinding.inflate(layoutInflater)
        setContentView(binding.root)

        auth = FirebaseAuth.getInstance()

        setupClickListeners()
    }

    private fun setupClickListeners() {
        // Register button
        binding.btnRegister.setOnClickListener {
            performRegister()
        }

        // Login link
        binding.tvLogin.setOnClickListener {
            finish() // Go back to login
        }
    }

    private fun performRegister() {
        val name = binding.etName.text.toString().trim()
        val email = binding.etEmail.text.toString().trim()
        val password = binding.etPassword.text.toString().trim()
        val confirmPassword = binding.etConfirmPassword.text.toString().trim()

        // Validation
        if (name.isEmpty()) {
            binding.tilName.error = getString(R.string.error_name_empty)
            return
        }
        binding.tilName.error = null

        if (email.isEmpty()) {
            binding.tilEmail.error = getString(R.string.error_email_empty)
            return
        }
        binding.tilEmail.error = null

        if (password.isEmpty()) {
            binding.tilPassword.error = getString(R.string.error_password_empty)
            return
        }
        binding.tilPassword.error = null

        if (password.length < 6) {
            binding.tilPassword.error = getString(R.string.error_password_short)
            return
        }
        binding.tilPassword.error = null

        if (password != confirmPassword) {
            binding.tilConfirmPassword.error = getString(R.string.error_passwords_mismatch)
            return
        }
        binding.tilConfirmPassword.error = null

        showProgress(true)

        auth.createUserWithEmailAndPassword(email, password)
            .addOnCompleteListener(this) { task ->
                if (task.isSuccessful) {
                    // Update user profile with name
                    val user = auth.currentUser
                    val profileUpdates = UserProfileChangeRequest.Builder()
                        .setDisplayName(name)
                        .build()

                    user?.updateProfile(profileUpdates)
                        ?.addOnCompleteListener { profileTask ->
                            showProgress(false)
                            if (profileTask.isSuccessful) {
                                Toast.makeText(this, R.string.register_success, Toast.LENGTH_SHORT).show()
                                startActivity(Intent(this, MainActivity::class.java))
                                finish()
                            }
                        }
                } else {
                    showProgress(false)
                    Toast.makeText(this, R.string.error_register_failed, Toast.LENGTH_LONG).show()
                }
            }
    }

    private fun showProgress(show: Boolean) {
        binding.progressBar.visibility = if (show) View.VISIBLE else View.GONE
        binding.btnRegister.isEnabled = !show
    }
}
