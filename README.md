# F5 Studio

A personal, fully offline Mac app for turning long scripts (study reviewers, lecture notes,
character-voiced tutoring scripts) into long-form audio with [F5-TTS](https://github.com/SWivid/F5-TTS)
voice cloning.

Write or paste a script, fix pronunciations, pick a 5–10 second reference voice, and F5 Studio
generates it one paragraph at a time on the Apple GPU, with pause and resume, redoing single lines,
and a merged MP3 in `~/f5-tts/exports/<project>/` at the end (with a Show in Finder button).

- **Script**: paste one in (e.g. written with Claude), or pick one written by the Cogitator's
  Scriptorium (a separate local study app; see app/README.md). A fact check flags numbers or citations
  that went missing compared to the source.
- **Pronunciation**: a shared find-and-replace list (Latin terms, names, acronyms), plus numbers
  turned into words, before anything is spoken.
- **Voice**: drop in a clip; it's trimmed, converted to 24 kHz and transcribed with Whisper.
- **Generate**: a queue that survives restarts. Clips are keyed by their text, so editing one line
  only redoes that line. Lines with an unusual pace get flagged for a listen.
- **Export**: everything, or only the finished sections, with adjustable pauses. Long projects (over
  5 hours to generate, adjustable) can optionally be split into parts that save themselves to the exports
  folder as each one finishes.

Everything stays on the Mac. There are no accounts or paid APIs, and the Hugging Face hub isn't
contacted after the first model download.

## Setup (Apple Silicon, macOS 13+)

The app expects to live at `~/f5-tts`, with F5-TTS installed in `~/f5-tts/.venv`.

```bash
git clone https://github.com/lloydonix/f5-studio.git ~/f5-tts
cd ~/f5-tts
brew install python@3.11 ffmpeg
python3.11 -m venv .venv
.venv/bin/pip install f5-tts
```

Download the models once (F5-TTS v1, the Vocos vocoder, and Whisper for transcribing voices):

```bash
.venv/bin/hf download SWivid/F5-TTS F5TTS_v1_Base/model_1250000.safetensors F5TTS_v1_Base/vocab.txt
.venv/bin/hf download charactr/vocos-mel-24khz config.yaml pytorch_model.bin
.venv/bin/hf download openai/whisper-large-v3-turbo --exclude "*.bin" --exclude "*.msgpack" --exclude "*.h5"
```

F5-TTS runs long paragraphs as parallel batches, and concurrent work on the Apple GPU crashes Metal.
Patch it to run them one at a time:

```bash
sed -i '' 's/with ThreadPoolExecutor() as executor:/with ThreadPoolExecutor(max_workers=1) as executor:/' \
  .venv/lib/python3.11/site-packages/f5_tts/infer/utils_infer.py
```

Build the Mac app (needs the Xcode command line tools). It installs to `~/Applications/F5 Studio.app`:

```bash
app/desktop/build.sh
```

Open **F5 Studio**. It starts its local server on `127.0.0.1:8799`, and quitting the app stops it.
More on how it's put together is in [app/README.md](app/README.md).

## Licenses and use

F5-TTS's code is MIT-licensed, but its **pretrained model weights are CC-BY-NC 4.0: non-commercial
use only**. Only clone voices of people who have agreed to it.

`launcher/` holds the original one-click launcher for F5-TTS's own Gradio web UI.
