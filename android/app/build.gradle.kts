plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.google.gms.google.services)
}

android {
    namespace = "com.iknowu.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.iknowu.app"
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        signingConfig = signingConfigs.getByName("debug")
        experimentalProperties["android.ndk.suppressMinSdkVersionError"] = 21
    }

    flavorDimensions += "platform"
    productFlavors {
        create("slate") {
            dimension = "platform"
            minSdk = 16
            buildConfigField("boolean", "GOOGLE_SIGN_IN", "false")
        }
        create("legacy") {
            dimension = "platform"
            minSdk = 19
            buildConfigField("boolean", "GOOGLE_SIGN_IN", "false")
        }
        create("modern") {
            dimension = "platform"
            minSdk = 23
            buildConfigField("boolean", "GOOGLE_SIGN_IN", "true")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            isDebuggable = false
            isJniDebuggable = false
            signingConfig = signingConfigs.getByName("debug")
            multiDexEnabled = false
            versionNameSuffix = "1.0"
        }
        getByName("debug") {
            versionNameSuffix = "1.0"
            isDebuggable = true
            isJniDebuggable = true
            signingConfig = signingConfigs.getByName("debug")
            isMinifyEnabled = false
            isShrinkResources = false
            multiDexEnabled = true
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    buildFeatures {
        viewBinding = true
        buildConfig = true
    }
    dependenciesInfo {
        includeInApk = true
        includeInBundle = true
    }
    buildToolsVersion = "37.0.0"
    ndkVersion = "28.2.13676358"
}

dependencies {
    // AppCompat
    "slateImplementation"("androidx.appcompat:appcompat:1.6.1")
    "legacyImplementation"("androidx.appcompat:appcompat:1.6.1")
    "modernImplementation"(libs.androidx.appcompat)

    // ConstraintLayout
    "slateImplementation"("androidx.constraintlayout:constraintlayout:2.1.4")
    "legacyImplementation"("androidx.constraintlayout:constraintlayout:2.1.4")
    "modernImplementation"(libs.androidx.constraintlayout)

    // Core KTX
    "slateImplementation"("androidx.core:core-ktx:1.10.1")
    "legacyImplementation"("androidx.core:core-ktx:1.10.1")
    "modernImplementation"(libs.androidx.core.ktx)

    // Credentials
    "legacyImplementation"("androidx.credentials:credentials:1.2.0")
    "modernImplementation"("androidx.credentials:credentials:1.6.0")
    "modernImplementation"("androidx.credentials:credentials-play-services-auth:1.6.0")

    // Firebase Auth - slate/legacy use older version, modern uses latest
    "slateImplementation"("com.google.firebase:firebase-auth:21.0.1")
    "legacyImplementation"("com.google.firebase:firebase-auth:22.3.1")
    "modernImplementation"(libs.firebase.auth)

    // Google ID
    "modernImplementation"(libs.googleid)

    // Google Play Services Auth (for Google Sign-In)
    "modernImplementation"("com.google.android.gms:play-services-auth:20.7.0")

    // Material
    "slateImplementation"("com.google.android.material:material:1.9.0")
    "legacyImplementation"("com.google.android.material:material:1.9.0")
    "modernImplementation"(libs.material)

    // Testing
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
}

tasks.register("installOnAll") {
    group = "install"
    description = "Installs the debug APK on all compatible connected devices (API 21+)."
    dependsOn("assembleLegacyDebug")

    doLast {
        val adb = "C:\\Program Files (x86)\\Android\\android-sdk\\platform-tools\\adb.exe"
        val devicesProcess = ProcessBuilder(adb, "devices").start()
        val devicesOutput = devicesProcess.inputStream.bufferedReader().readText()
        devicesProcess.waitFor()
        
        val devices = devicesOutput.lines()
            .filter { it.trim().endsWith("device") }
            .map { it.split("\t")[0] }

        if (devices.isEmpty()) {
            println("No devices connected via ADB.")
            return@doLast
        }

        devices.forEach { deviceId ->
            // Check SDK version
            val sdkProcess = ProcessBuilder(adb, "-s", deviceId, "shell", "getprop", "ro.build.version.sdk").start()
            val sdkVersionStr = sdkProcess.inputStream.bufferedReader().readText().trim()
            sdkProcess.waitFor()
            
            val sdkVersion = sdkVersionStr.toIntOrNull() ?: 0
            
            if (sdkVersion >= 21) {
                println("Installing on $deviceId (API $sdkVersion)...")
                val installProcess = ProcessBuilder(adb, "-s", deviceId, "install", "-r", "build/outputs/apk/legacy/debug/app-legacy-debug.apk")
                    .inheritIO()
                    .start()
                
                val exitCode = installProcess.waitFor()
                if (exitCode != 0) {
                    println("❌ Failed to install on $deviceId. If you see 'INSTALL_FAILED_USER_RESTRICTED', please accept the prompt on the device screen.")
                } else {
                    println("✅ Successfully installed on $deviceId.")
                }
            } else {
                println("⚠️ Skipping $deviceId: API level $sdkVersion is below the required 21.")
            }
        }
    }
}