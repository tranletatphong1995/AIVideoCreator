# AI Video Creator

PyQt desktop tool for creating narrated videos from an idea prompt.

## Features

- Ollama brainstorms a structured video plan.
- VieNeu TTS generates narration audio.
- HTML mode renders static designed scenes through Playwright.
- Fooocus image-story mode generates illustration images through bundled Fooocus-API.
- Ollama subtitle agent creates frame-timed subtitle cues.
- Optional Online ChatGPT mode uses `ima2-gen` via `npx` for ChatGPT text tasks and GPT image generation.
- MoviePy assembles images/video clips, subtitles, narration, and optional background music.

## Quick Start

Double-click:

```bat
run.bat
```

The launcher creates or repairs the app virtual environment, installs dependencies
with the VieNeu Windows CPU wheel index, checks Playwright Chromium, then starts
the UI. On a clean Windows machine it will also try to install Python 3.11 with
`winget` if Python is missing.

Inside the app, use the setup buttons before the first render:

- `Cài/kiểm tra môi trường`: installs or verifies Python packages, Playwright,
  VieNeu TTS, and the runtime needed by the selected AI mode.
- `Cài/Test TTS`: installs VieNeu if needed, downloads the first TTS assets, and
  writes a short test WAV file.
- `Cài Ollama/model`: installs Ollama with `winget` when missing, starts the
  Ollama server, and pulls the selected/default model.
- `API`: starts the bundled Fooocus API engine and lets its bootstrap install
  Fooocus API dependencies and download models on first run.
- `Login ChatGPT` and `Start ima2`: verify/install Node.js LTS with `winget`
  before running the required `npx` commands.

The machine still needs internet access. GPU drivers/CUDA are not installed by
the app; install vendor drivers separately if you want accelerated Fooocus.

## Fooocus API

Fooocus-API is included under:

```text
engines/Fooocus-API
```

In the UI, click `API` to start it. First startup can take a long time because
Fooocus-API may install Python dependencies and download SDXL models. The
button uses `engines/Fooocus-API/start_fooocus_api.bat` by default.

The default endpoint is:

```text
http://127.0.0.1:8888
```

Large model files and runtime outputs are intentionally ignored by git.

## Online ChatGPT / ima2-gen mode

Online mode is optional. Local Ollama/Fooocus remains the default.

1. In the UI, choose `Online ChatGPT/ima2-gen`.
2. Click `Login ChatGPT` once. The app will install/check Node.js LTS first, or
   you can run:

```bat
npx --yes @openai/codex login
```

3. Click `Start ima2`, or run:

```bat
npx --yes ima2-gen serve
```

When the image-story checkbox is enabled in online mode, images are generated through `ima2-gen` and saved under `temp_slides/ima2_images`.
