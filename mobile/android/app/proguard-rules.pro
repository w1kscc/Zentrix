# JNI-ядро tun2socks: нативный код вызывает эти классы по именам.
-keep class hev.htproxy.** { *; }
-keep class com.zentrix.connect.vpn.** { *; }
-keepclasseswithmembernames class * { native <methods>; }
