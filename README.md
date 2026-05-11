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

The launcher creates or repairs the app virtual environment, installs dependencies,
checks Playwright Chromium, then starts the UI.

## Fooocus API

Fooocus-API is included under:

```text
engines/Fooocus-API
```

In the UI, click `API` to start it. First startup can take a long time because
Fooocus-API may install Python dependencies and download SDXL models.

The default endpoint is:

```text
http://127.0.0.1:8888
```

Large model files and runtime outputs are intentionally ignored by git.

## Online ChatGPT / ima2-gen mode

Online mode is optional. Local Ollama/Fooocus remains the default.

1. Install Node.js 20+.
2. In the UI, choose `Online ChatGPT/ima2-gen`.
3. Click `Login ChatGPT` once, or run:

```bat
npx --yes @openai/codex login
```

4. Click `Start ima2`, or run:

```bat
npx --yes ima2-gen serve
```

When the image-story checkbox is enabled in online mode, images are generated through `ima2-gen` and saved under `temp_slides/ima2_images`.
