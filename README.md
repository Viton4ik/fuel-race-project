# Fuel price race 1999–2026 

Vertical 1080x1920, 60 fps, 75 s bar-chart race: gasoline and diesel retail prices in US$ per litre for
EU-27, United Kingdom, Norway, Switzerland, Iceland, Türkiye (top-7 race) plus Serbia, Russia and China (pinned).

## Build
```
pip install -r requirements.txt      # plus ffmpeg and the Inter font (fonts-inter)
./make_video.sh
```
Steps:
1. `scripts/build_data.py`  raw official data (`data/raw/`) -> `data/prices_usd_monthly.csv`
2. `scripts/music.py`       synthesizes the original background track -> `build/music.wav`
3. `scripts/render.py`      draws every frame with Skia and encodes H.264 -> `build/race_silent.mp4`
   (`--preview 600 1500` saves single PNG frames into `build/frames/` for quick checks)
4. ffmpeg muxes video + music, loudness-normalised to -14 LUFS -> `output/`

## Customise
* `render.py`: `TOP_N`, `PINNED`, `T_RACE` (race length), `EVENTS` (captions), colours `C_GAS`/`C_DSL`.
* Font path is set in `FD` (Inter). Flags: `assets/flags/` rendered from flag-icons (MIT licence).

Data sources and method: `data/SOURCES.md`. YouTube text: `YOUTUBE_DESCRIPTION.md`.
