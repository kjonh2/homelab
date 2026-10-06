package com.iknowu.app

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.firebase.auth.FirebaseAuth
import com.iknowu.app.BuildConfig
import com.iknowu.app.databinding.ActivityLoginBinding

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private lateinit var auth: FirebaseAuth

    companion object {
        private const val TAG = "LoginActivity"
        private const val RC_GOOGLE_SIGN_IN = 9001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Initialize Google Sign-In for modern flavor
        if (BuildConfig.GOOGLE_SIGN_IN) {
            try {
                Class.forName("com.iknowu.app.GoogleSignInModern")
                    .getMethod("init")
                    .invoke(null)
                Log.d(TAG, "Google Sign-In initialized for modern flavor")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to init Google Sign-In", e)
            }
        }

        auth = FirebaseAuth.getInstance()

        // Check if user is already logged in
        if (auth.currentUser != null) {
            navigateToMain()
            return
        }

        // Hide Google Sign-In button if not available
        if (!googleSignInHelper.isAvailable()) {
            Log.d(TAG, "Google Sign-In not available")
            binding.btnGoogleSignin.visibility = View.GONE
        }

        setupClickListeners()
    }

    private fun setupClickListeners() {
        binding.btnLogin.setOnClickListener { performLogin() }
        binding.btnGoogleSignin.setOnClickListener { performGoogleSignIn() }
        binding.tvForgotPassword.setOnClickListener { performPasswordReset() }
        binding.tvRegister.setOnClickListener {
            startActivity(Intent(this, RegisterActivity::class.java))
        }
    }

    private fun performLogin() {
        val email = binding.etEmail.text.toString().trim()
        val password = binding.etPassword.text.toString().trim()

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

        showProgress(true)

        auth.signInWithEmailAndPassword(email, password)
            .addOnCompleteListener(this) { task ->
                showProgress(false)
                if (task.isSuccessful) {
                    Toast.makeText(this, R.string.login_success, Toast.LENGTH_SHORT).show()
                    navigateToMain()
                } else {
                    val msg = task.exception?.message ?: getString(R.string.error_auth_failed)
                    Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
                }
            }
    }

    private fun performGoogleSignIn() {
        Log.d(TAG, "performGoogleSignIn called")
        showProgress(true)
        googleSignInHelper.signIn(this, getString(R.string.default_web_client_id))
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == RC_GOOGLE_SIGN_IN) {
            showProgress(false)
            Log.d(TAG, "Google Sign-In result received")

            val idToken = googleSignInHelper.handleSignInResult(data)
            if (idToken != null) {
                googleSignInHelper.firebaseAuthWithGoogle(
                    idToken, auth,
                    onSuccess = {
                        Toast.makeText(this, R.string.login_success, Toast.LENGTH_SHORT).show()
                        navigateToMain()
                    },
                    onError = { error ->
                        Toast.makeText(this, error, Toast.LENGTH_LONG).show()
                    }
                )
            } else {
                Toast.makeText(this, R.string.error_google_signin, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun performPasswordReset() {
        val email = binding.etEmail.text.toString().trim()

        if (email.isEmpty()) {
            binding.tilEmail.error = getString(R.string.error_email_empty)
            return
        }
        binding.tilEmail.error = null

        showProgress(true)

        auth.sendPasswordResetEmail(email)
            .addOnCompleteListener { task ->
                showProgress(false)
                if (task.isSuccessful) {
                    Toast.makeText(this, R.string.password_reset_sent, Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this, R.string.error_auth_failed, Toast.LENGTH_LONG).show()
                }
            }
    }

    private fun navigateToMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    private fun showProgress(show: Boolean) {
        binding.progressBar.visibility = if (show) View.VISIBLE else View.GONE
        binding.btnLogin.isEnabled = !show
        binding.btnGoogleSignin.isEnabled = !show
    }
}
