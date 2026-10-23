# ABAJ TV OS — ZTE ZXV10 B866 / MTS IPTV

This is a **non-flashable development starter** for the exact ZTE ZXV10 B866 **IPTV** device. It is not an Android firmware image. Never flash an OTT, B866V2 or generic S905X ROM to this device.

Hardware reference: Amlogic S905X, 2 GB RAM, 8 GB eMMC, Android TV 9/10 (verify actual revision on device).

## Safe work already included
- Native Android TV HOME launcher in `launcher/`, separate from existing ABAJ TV Standalone.
- Opens existing `ai.abaj.tv.standalone` using Android's package manager.
- Has remote-friendly buttons for ABAJ TV, Wi-Fi and Android settings.
- Can work as default Home only if operator software allows another launcher.
- No root, bootloader unlocking, flashing or modifications to ABAJ TV Standalone.

## Read-only device inspection

Connect with authorized ADB and run:

```bash
adb devices
bash probe/read_only.sh
```

Output is `probe/b866-diagnostics.txt`. Review before sharing. Do not send serial numbers, MACs, tokens, Widevine/DRM keys or full system partitions.

## Build the HOME APK

Requires JDK 17, Android SDK 35, Gradle 8.9.

```bash
gradle -p firmware/b866-iptv/launcher :app:assembleDebug
```

Result: `firmware/b866-iptv/launcher/app/build/outputs/apk/debug/app-debug.apk`.

Select the new Home app only when your firmware offers that choice. To revert, reselect the MTS launcher in system Home settings or uninstall the separate HOME app.

## Before attempting a real Android ROM

1. Confirm board revision, device-tree ID, CPU, memory, Android version and AVB/bootloader state.
2. Obtain verified **matching IPTV** stock firmware and a tested recovery plan.
3. Check availability and licensing of vendor GPU/VPU, HDMI, Wi-Fi, Bluetooth, audio, IR, DRM drivers and kernel sources.
4. Boot a compatible OS non-destructively, test playback and input, then decide whether any flashable image is viable.

Do not advertise Android 15/16 for this box before a working hardware-specific port exists.


## Verified research for this box (2026-10-23)

Physical label provided by owner: **MTS IPTV ТВ-приставка, ZTE ZXV10 B866**.
Previously shared About-device screen indicates **Android 9**, firmware
**V81111371.1041**, **PL20210417**, bootloader **V0004** and 2021 security patch.
These values are **reported from prior photo**, not independently read via ADB yet.

References:
- [MTS support](https://support.mts.ru/domashnii_internet_i_tv/oborudovanie/rukovodstvo-po-ekspluatatsii-tv-pristavok-msk) distinguishes IPTV B866 from OTT products.
- [Android TV Guide B866 IPTV](https://www.androidtv-guide.com/pay-tv-provider/mts-iptv-box/) identifies Amlogic S905X / 2 GB / 8 GB / Android TV 9–10.
- [ZTE B866V2K](https://www.zte.com.cn/global/product_index/home_media_center_en/ip-stb/ZXV10_B866V2K/ZXV10_B866V2K.html) is a **different** Android 11 device (Cortex-A35, Mali-G31). It is NOT a compatible Android 11 image for this B866.
- [Community IPTV/OTT warning](https://4pda.to/forum/index.php?showtopic=993178&st=4200) emphasizes that mixing IPTV, OTT and V2 firmwares can permanently brick hardware.

**Result:** No verified Android 15/16 image for the original MTS B866 IPTV was identified. ROM porting is blocked pending matching vendor binaries, board/recovery research and physical device tests. This repository does **not** promise an updated Android system.

## Home app 0.2.0

Safe read-only info page (accessible directly with the remote, no PC required): manufacturer, model, device, board, hardware, bootloader, Android release, build, patch and primary ABI. This page intentionally excludes serial numbers, MAC addresses, identifiers and DRM data. Photograph that page for ROM compatibility checks.

The Home screen adds a persisted on/off switch for automatic ABAJ TV launch after a **new boot**. When disabled, the menu stays visible. Neither setting requires nor requests privileged Android access.

The new APK is a separate installable package, not a firmware, and should be tested first before selecting it as the default HOME application. MTS firmware may disallow replacing its Home launcher. To undo: reselect default Home in system settings or uninstall `ai.abaj.tv.home`.

Source/build location: `firmware/b866-iptv/launcher`.
