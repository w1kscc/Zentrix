plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.sharingconnect"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.sharingconnect"
        minSdk = 29
        targetSdk = 35
        versionCode = 15
        versionName = "1.2.2"
        ndk {
            // Go-ядро весит >100 МБ на ABI. Минимальный SDK 29 — все такие
            // устройства ARM: берём только arm64, APK сжимаем (см. packaging).
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
        // Ядро весит >100 МБ на ABI: оставляем только ARM (x86-библиотеки
        // из AAR в APK не нужны) и включаем сжатие .so вместо хранения
        // их несжатыми (useLegacyPackaging=false).
        jniLibs {
            // Сжимаем .so в APK (распаковываются при установке):
            // несжатое Go-ядро весит 126 МБ, сжатое — вдвое-втрое меньше.
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
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.core:core-ktx:1.15.0")

    // QR-сканер адреса прокси из вкладки «Шеринг» Zentrix
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")

    // tun2socks (hev-socks5-tunnel): скачивается scripts/fetch_tun2socks.py
    implementation(files("libs/hiddify-core.aar"))
    implementation("androidx.compose.material:material-icons-extended")

    testImplementation("junit:junit:4.13.2")
}
