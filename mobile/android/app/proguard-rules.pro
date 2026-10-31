# JNI-мост tun2socks
-keep class com.sharingconnect.vpn.Tun2Socks { *; }

# Go-ядро (gomobile) вызывает эти классы из C по JNI-именам:
# переименование методов R8 ломает openTun/колбэки PlatformInterface.
-keep class com.hiddify.core.** { *; }
-keep class com.sharingconnect.vpn.CorePlatform { *; }
-keep class com.sharingconnect.vpn.SharingVpnService { *; }
-keep class com.sharingconnect.vpn.AppContext { *; }
-keepclasseswithmembernames class * { native <methods>; }
