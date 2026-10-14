#!/bin/bash
# Optional installation adapter for AVFoundation cameras whose native rate is
# 30000/1001, not 30 (e.g. the 2012 MacBook Air FaceTime HD camera).
# Install as <helper-data>/bin/ffmpeg, with the signed, unmodified executable at
# <helper-data>/libexec/ffmpeg. Probes and non-camera inputs pass through unchanged.
set -euo pipefail
args=("$@")
format=""
rate_index=-1
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[i]}" in
    -f) format="${args[i+1]:-}" ;;
    -framerate) rate_index=$((i+1)) ;;
    -i)
      if [[ "$format" == avfoundation && $rate_index -ge 0 &&
            "${args[rate_index]:-}" == 30 && "${args[i+1]:-}" != none:* ]]; then
        args[rate_index]="30000/1001"
      fi
      format=""
      rate_index=-1
      ;;
  esac
done
here="$(cd "$(dirname "$0")" && pwd)"
exec "$here/../libexec/ffmpeg" "${args[@]}"
