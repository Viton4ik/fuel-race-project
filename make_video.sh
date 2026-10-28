#!/usr/bin/env bash
# Full pipeline: data -> silent video -> music -> final MP4 (1080x1920, 60 fps, AAC 192k, -14 LUFS)
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/build_data.py
python3 scripts/music.py
scripts/render_parallel.sh
ffmpeg -y -loglevel error -i build/race_silent.mp4 -i build/music.wav \
  -filter_complex "[1:a]loudnorm=I=-14:TP=-1.5:LRA=9[a]" -map 0:v -map "[a]" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart \
  output/fuel_prices_1999_2026_shorts_75s.mp4
echo "done: output/fuel_prices_1999_2026_shorts_75s.mp4"
