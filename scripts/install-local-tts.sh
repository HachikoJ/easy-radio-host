#!/usr/bin/env bash
set -euo pipefail

model_dir="${1:-/opt/easy-radio-host/models/vits-melo-tts-zh_en}"
base_url="${HF_MIRROR_BASE:-https://hf-mirror.com/csukuangfj/vits-melo-tts-zh_en/resolve/main}"

declare -A expected=(
  [model.onnx]="bf30582eb1b012250a35b1a4a80e7dfbcf8485e7bb9de0d95efbbeef0e4ad86d"
  [lexicon.txt]="7236884b02435ac5d10cf69b4be40a61b45aa676b5300f0e412f185748fee528"
  [tokens.txt]="d18664a7e12bd7ea1022ddaf951e534e136815016c5a809d6b64156bffb4369d"
  [LICENSE]="88a50e5a02bbc2a5c2f084dc19da751aa97b1690f5fda76cd8005c8634d1ca70"
)

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/tingjian-tts.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

sudo install -d -o root -g root -m 755 "$model_dir"
for filename in "${!expected[@]}"; do
  target="$model_dir/$filename"
  if [[ -f "$target" ]] && \
      [[ "$(sha256sum "$target" | awk '{print $1}')" == "${expected[$filename]}" ]]; then
    echo "verified $target"
    continue
  fi
  staged="$work_dir/$filename"
  curl -fL --retry 4 --retry-delay 2 --connect-timeout 15 \
    -o "$staged" "$base_url/$filename"
  actual="$(sha256sum "$staged" | awk '{print $1}')"
  if [[ "$actual" != "${expected[$filename]}" ]]; then
    echo "checksum mismatch for $filename: expected ${expected[$filename]}, got $actual" >&2
    exit 1
  fi
  sudo install -o root -g root -m 644 "$staged" "$target"
  echo "installed $target"
done
