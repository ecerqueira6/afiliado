[app]
title = Afiliado ML
package.name = afiliadoml
package.domain = org.afiliado
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,requests,urllib3,idna,charset-normalizer,certifi,beautifulsoup4,soupsieve,typing_extensions

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

# versão estável do python-for-android (compatível com Kivy 2.3.0 e Python 3.11)
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
