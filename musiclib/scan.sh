#!/usr/bin/env bash
# 生成 easy-radio-host 播放列表
# 输出格式：每行一个 mp3 相对路径（app 端 fetch_library 解析格式）
# 用法：放好歌曲后运行  bash /opt/easy-radio-host/musiclib/scan.sh
#
# 产物：/opt/easy-radio-host/musiclib/songs.txt
#       可通过 HTTP 提供给主应用的 NAS_LIST_URL（在线 API 部署无需使用）

set -euo pipefail
MP="/opt/easy-radio-host/musiclib"
OUT="$MP/songs.txt"
SRC="$MP/songs"

# 递归收集音频文件，按相对路径排序后写入（含子目录，路径前缀 songs/）
find "$SRC" -type f \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.flac' \
  -o -iname '*.m4a' -o -iname '*.aac' -o -iname '*.ogg' \) \
  -printf '%P\n' 2>/dev/null | sort | sed "s|^|songs/|" > "$OUT"

count=$(wc -l < "$OUT")
echo "已生成 $OUT ，共 $count 首歌"
if [ "$count" -eq 0 ]; then
  echo "提示：当前 songs/ 为空。放入 mp3 后再运行本脚本即可。"
fi
