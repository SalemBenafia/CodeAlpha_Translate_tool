#!/usr/bin/env bash
# One-time setup: Python deps, Piper TTS voices, local LibreTranslate engine.
set -euo pipefail
cd "$(dirname "$0")"

LANGS="en,es,fr,de,it,pt,ru,ar,hi,zh"
VOICES=(
  en_US-lessac-medium
  es_ES-davefx-medium
  fr_FR-siwis-medium
  de_DE-thorsten-medium
  it_IT-paola-medium
  pt_BR-faber-medium
  ru_RU-dmitri-medium
  ar_JO-kareem-medium
  hi_IN-pratham-medium
  zh_CN-huayan-medium
)

echo "==> 1/3  Python environment (FastAPI + Piper)"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo "==> 2/3  Piper voices (~60 MB each, skipped if already present)"
mkdir -p voices
for voice in "${VOICES[@]}"; do
  # A voice needs both files; an interrupted download leaves only the .onnx.
  if [ -f "voices/$voice.onnx" ] && [ -f "voices/$voice.onnx.json" ]; then
    echo "    have $voice"
  else
    echo "    downloading $voice"
    .venv/bin/python -m piper.download_voices --download-dir voices "$voice"
  fi
done

echo "==> 3/3  LibreTranslate engine (Docker)"
if ! command -v docker >/dev/null 2>&1; then
  echo "    Docker not found — skipping."
  echo "    Either install Docker, or use the hosted API:"
  echo "      LT_URL=https://libretranslate.com LT_API_KEY=your-key ./run.sh"
elif docker ps -a --format '{{.Names}}' | grep -qx libretranslate; then
  docker start libretranslate >/dev/null
  echo "    container already exists — started."
else
  docker run -d --name libretranslate -p 5000:5000 \
    libretranslate/libretranslate:latest --load-only "$LANGS" --update-models >/dev/null
  echo "    container created. First boot downloads models (a few minutes)."
fi

echo
echo "Done. Start the tool with:  ./run.sh   ->  http://localhost:3000"
