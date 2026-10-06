package com.iknowu.app

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.firebase.auth.FirebaseAuth
import com.iknowu.app.databinding.ActivityMainBinding
import com.iknowu.app.homestatus.HomeStatusFragment

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

        // Display user info in the header
        val user = auth.currentUser
        binding.sampleText.text =
            "Bem-vindo, ${user?.displayName ?: user?.email ?: "Utilizador"}!"

        binding.bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_inicio -> switchTo(HomeStatusFragment())
                R.id.nav_impressora -> switchTo(PrinterControlFragment())
                R.id.nav_servicos -> switchTo(ServicesShortcutFragment())
                R.id.nav_ficheiros -> switchTo(FilesCategoryFragment())
                R.id.nav_perfil -> switchTo(ProfileFragment())
                else -> false
            }
        }

        if (savedInstanceState == null) {
            binding.bottomNav.selectedItemId = R.id.nav_inicio
        }
    }

    private fun switchTo(fragment: Fragment): Boolean {
        supportFragmentManager.beginTransaction()
            .replace(R.id.nav_container, fragment)
            .commit()
        return true
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
