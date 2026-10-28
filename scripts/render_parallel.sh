#!/usr/bin/env bash
# Render the video in N parallel chunks (default: number of CPU cores) and join them losslessly.
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-$(nproc)}
TOTAL=$(python3 -c "import sys; sys.argv=['x']; sys.path.insert(0,'scripts'); import render; print(render.NF)" 2>/dev/null)
CH=$(( (TOTAL + N - 1) / N ))
rm -f build/chunks.txt
for i in $(seq 0 $((N-1))); do
  python3 scripts/render.py --start $((i*CH)) --end $(((i+1)*CH)) --out build/chunk_$i.mp4 > build/render_$i.log 2>&1 &
  echo "file 'chunk_$i.mp4'" >> build/chunks.txt
done
wait
ffmpeg -y -loglevel error -f concat -safe 0 -i build/chunks.txt -c copy build/race_silent.mp4
echo "joined build/race_silent.mp4"
