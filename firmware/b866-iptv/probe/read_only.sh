#!/usr/bin/env bash
set -euo pipefail
OUT="$(cd "$(dirname "$0")" && pwd)/b866-diagnostics.txt"
command -v adb >/dev/null || { echo 'adb not installed' >&2; exit 1; }
adb get-state >/dev/null || { echo 'ADB device not available/authorized' >&2; exit 1; }
{
  printf 'ABAJ TV B866 read-only diagnostics\n'
  printf '==================================\n'
  for p in \
    ro.product.manufacturer ro.product.model ro.product.device \
    ro.product.board ro.board.platform ro.hardware ro.boot.hardware \
    ro.build.version.release ro.build.version.sdk \
    ro.build.version.security_patch ro.product.cpu.abilist \
    ro.bootloader ro.boot.verifiedbootstate ro.boot.flash.locked \
    ro.boot.vbmeta.device_state ro.boot.slot_suffix; do
    printf '%-34s ' "$p"
    adb shell getprop "$p" | tr -d '\r'
  done
  printf '\n/proc/partitions (names and sizes only):\n'
  adb shell cat /proc/partitions
  printf '\nAvailable space:\n'
  adb shell df -h /data
} > "$OUT"
printf 'Saved: %s\n' "$OUT"
