package com.iknowu.app

import android.app.Activity
import android.content.Intent
import com.google.firebase.auth.FirebaseAuth

/**
 * Google Sign-In helper interface.
 * Each flavor provides its own implementation.
 */
interface GoogleSignInHelper {
    fun isAvailable(): Boolean
    fun signIn(activity: Activity, webClientId: String)
    fun handleSignInResult(data: Intent?): String?
    fun firebaseAuthWithGoogle(idToken: String?, auth: FirebaseAuth, onSuccess: () -> Unit, onError: (String) -> Unit)
}

/**
 * Factory to get the appropriate GoogleSignInHelper implementation.
 * The modern flavor overrides this with GoogleSignInHelperImpl.
 */
var googleSignInHelper: GoogleSignInHelper = object : GoogleSignInHelper {
    override fun isAvailable(): Boolean = false
    override fun signIn(activity: Activity, webClientId: String) {}
    override fun handleSignInResult(data: Intent?): String? = null
    override fun firebaseAuthWithGoogle(idToken: String?, auth: FirebaseAuth, onSuccess: () -> Unit, onError: (String) -> Unit) {
        onError("Google Sign-In not available")
    }
}
