package com.iknowu.app

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.iknowu.app.databinding.ActivityMainBinding
import com.google.firebase.auth.FirebaseAuth

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var auth: FirebaseAuth

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Check if user is logged in
        auth = FirebaseAuth.getInstance()
        if (auth.currentUser == null) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Display user info
        val user = auth.currentUser
        val welcomeText = "Bem-vindo, ${user?.displayName ?: user?.email ?: "Utilizador"}!"
        binding.sampleText.text = welcomeText
    }

    /**
     * Returns a greeting string. Uses the native library on API 21+,
     * and a pure Kotlin fallback on older devices.
     */
    private fun stringFromJNI(): String {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            try {
                nativeStringFromJNI()
            } catch (e: UnsatisfiedLinkError) {
                getString(R.string.app_name)
            }
        } else {
            getString(R.string.app_name)
        }
    }

    private external fun nativeStringFromJNI(): String

    companion object {
        init {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                try {
                    System.loadLibrary("iknowu")
                } catch (e: UnsatisfiedLinkError) {
                    // Native library not available on this device
                }
            }
        }
    }
}
