package com.iknowu.app

import android.app.Activity
import android.content.Intent
import android.util.Log
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider

/**
 * Modern flavor (API 23+) Google Sign-In implementation.
 * This file is only compiled for the 'modern' flavor.
 */
object GoogleSignInModern {

    private const val TAG = "GoogleSignInModern"

    /**
     * Initialize the Google Sign-In helper for modern flavor.
     * This replaces the default no-op implementation.
     */
    fun init() {
        googleSignInHelper = object : GoogleSignInHelper {
            override fun isAvailable(): Boolean = true

            override fun signIn(activity: Activity, webClientId: String) {
                Log.d(TAG, "Starting Google Sign-In...")

                val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
                    .requestIdToken(webClientId)
                    .requestEmail()
                    .build()

                val client: GoogleSignInClient = GoogleSignIn.getClient(activity, gso)
                val signInIntent = client.signInIntent
                activity.startActivityForResult(signInIntent, 9001)
            }

            override fun handleSignInResult(data: Intent?): String? {
                Log.d(TAG, "Handling Google Sign-In result...")
                return try {
                    val task = GoogleSignIn.getSignedInAccountFromIntent(data)
                    val account = task.getResult(com.google.android.gms.common.api.ApiException::class.java)
                    account.idToken
                } catch (e: Exception) {
                    Log.e(TAG, "Error handling result", e)
                    null
                }
            }

            override fun firebaseAuthWithGoogle(
                idToken: String?,
                auth: FirebaseAuth,
                onSuccess: () -> Unit,
                onError: (String) -> Unit
            ) {
                if (idToken == null) {
                    onError("ID token is null")
                    return
                }
                try {
                    val credential = GoogleAuthProvider.getCredential(idToken, null)
                    auth.signInWithCredential(credential)
                        .addOnCompleteListener { task ->
                            if (task.isSuccessful) onSuccess()
                            else onError(task.exception?.message ?: "Sign-In failed")
                        }
                } catch (e: Exception) {
                    Log.e(TAG, "Firebase auth error", e)
                    onError(e.message ?: "Firebase auth error")
                }
            }
        }
    }
}
