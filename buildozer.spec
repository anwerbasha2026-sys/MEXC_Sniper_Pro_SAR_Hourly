[app]
title = MEXC Sniper Pro SAR Hourly
package.name = mexcsnipersar
package.domain = org.mexc.sniper
source.dir = .
source.include_exts = py,kv,json,txt,png,jpg
source.exclude_dirs = .git,.buildozer,bin,__pycache__
version = 1.0.0
requirements = python3,kivy==2.3.1,ccxt
orientation = landscape
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK
android.api = 33
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.private_storage = True
p4a.bootstrap = sdl2
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
