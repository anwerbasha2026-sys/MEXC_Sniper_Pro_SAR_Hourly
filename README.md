# MEXC Sniper Pro — SAR Hourly Android (ONN 3 tablet)

Android/Kivy project prepared for a landscape tablet interface and ARM64 Android devices.

## Strategy configuration
- Spot only; no leverage.
- PSAR `step=0.02`, `max_step=0.20`, using completed 1-hour candles.
- Entry confirmation: bullish PSAR reversal plus closed-candle 4-hour EMA200 filter.
- Exit: bearish PSAR reversal on a completed 1-hour candle or manual close.
- Demo mode is enabled by default. Real mode spends up to 99.5% of free USDT, leaving a buffer for fees/rounding.
- API credentials are not written to `settings.json`.

## Build APK with GitHub Actions
1. Upload the contents of this project folder to a GitHub repository (the `.github/workflows/build-onn3-apk.yml` file must be included at repository root).
2. Open **Actions** in GitHub and select **Build MEXC Sniper Pro APK (ONN 3 Tablet)**.
3. Select **Run workflow** and wait for the job to finish.
4. Download the artifact named `MEXC-Sniper-Pro-ONN3-APK`. It contains `MEXC_Sniper_Pro_SAR_Hourly_ONN3_debug.apk`.

You can also build on Linux with Java 17, Android SDK/NDK prerequisites, and Buildozer installed:

```bash
python -m pip install --upgrade buildozer
buildozer -v android debug
```

The APK produced by this workflow is a debug/test build, not a Play Store release. It must be installed and tested on the actual tablet before use.

## Safety and known limitations
- APK build and physical-device testing have not been completed in this workspace because Android SDK/NDK and Buildozer are not installed and package downloads are unavailable here.
- Live MEXC order execution has not been verified against an account. Keep Demo enabled until thoroughly tested.
- The current app tracks one position in process memory and does not yet restore/reconcile positions after Android kills the app. Check MEXC open orders and asset balances before restarting after a crash.
- API key permissions should allow Spot trading only; never enable withdrawals. Never share API secrets in chat.
- Using nearly all free USDT is high risk and can result in losing most of the balance.
