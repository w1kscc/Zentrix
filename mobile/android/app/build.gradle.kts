plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.zentrix.connect"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.zentrix.connect"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "1.3.0"
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    packagingOptions {
        jniLibs {
            useLegacyPackaging = true
            excludes += listOf("lib/x86/**", "lib/x86_64/**", "lib/mips/**", "lib/mips64/**")
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.10.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.core:core-ktx:1.15.0")

    // tun2socks (hev-socks5-tunnel): скачивается scripts/fetch_core.py
    implementation(files("libs/hev-socks5-tunnel.aar"))
}
