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
