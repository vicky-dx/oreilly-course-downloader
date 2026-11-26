# Standalone Android app (initial safe implementation)

A native Android application has been added under `android-app/`.

## Build
The GitHub Actions workflow at `.github/workflows/build-android-apk.yml` builds a debug APK.
1. Open the repository's Actions tab.
2. Run **Build Android APK**.
3. Download the `OReillyMobile-debug-apk` artifact from the successful run.
4. Extract and install `app-debug.apk` on an Android device.

## Current functionality
- Native Android UI.
- Direct HTTP/HTTPS file downloads using Android DownloadManager.
- Android system download notifications and a basic download status list.
- Files are saved under `Downloads/OReillyMobile/`.

## Important scope
This is not yet a native implementation of the repository's browser-automation/O'Reilly extraction engine. The existing Python application depends on Selenium, desktop Chrome/Chromium or Firefox, and browser automation components that cannot simply be embedded into Android. This Android app intentionally supports ordinary direct file URLs and files the user is authorized to download. It does not scrape authenticated O'Reilly course streams, bypass DRM, defeat bot detection, or circumvent subscription/access controls. For O'Reilly content, use official download/export functionality where available.

This is an initial APK-capable foundation, not a claim that all desktop CLI features have been ported.
