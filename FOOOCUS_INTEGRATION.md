# Fooocus image-story mode

## Why this integration uses an API adapter

The official Fooocus project is a standalone Gradio SDXL application. It has its
own model downloads, GPU/runtime requirements, and web UI lifecycle, so this app
does not import the whole Fooocus source tree into the PyQt process.

Instead, AI Video Creator can call a running Fooocus-compatible API server, save
one illustration per scene, then build a video from:

- Fooocus illustration images
- Ollama-generated frame-timed subtitle cues
- VieNeu TTS narration audio
- optional background music

## UI usage

1. Open `run.bat`.
2. Enable `Dùng Fooocus tạo ảnh minh họa + subtitle`.
3. Set `Fooocus API`, default: `http://127.0.0.1:8888`.
4. The bundled local API folder should already be selected:

```text
engines/Fooocus-API
```

5. Keep `Lệnh API` as `start_fooocus_api.bat`, then click `API` to start the server.
6. Create the video normally when the log says the API is ready.

The current adapter posts to:

```text
/v1/generation/text-to-image
```

It expects a response with either a `base64` image field or an image `url`.

The API start button opens the command in a separate console window. The bundled
launcher is:

```text
start_fooocus_api.bat
```

It creates a separate Fooocus API `.venv` with Python 3.10 and then starts
`main.py --host 127.0.0.1 --port 8888`. First launch can take a long time
because Fooocus-API may install dependencies and download SDXL models.

## Image styles

The style menu now includes: modern, news, education, corporate, minimal,
fantasy, science, eerie, cinematic, anime, nature, and historical. Fooocus mode
uses these as prompt style hints; HTML mode uses the same selection for its
color/design preset.

## Subtitle timing

Fooocus does not create text. The app creates subtitles separately with
`module_subtitle_agent.py`:

1. VieNeu TTS creates the narration audio.
2. The app reads the real audio duration.
3. Ollama creates subtitle cues with `start`, `end`, `start_frame`,
   `end_frame`, and `text`.
4. `video_assembler.py` overlays each cue only during its own time range.

If Ollama returns invalid JSON or fails, the subtitle agent falls back to
splitting narration into timed cues by sentence and text length.

## Output

When Fooocus mode is enabled, final files are named:

```text
fooocus_video_YYYYMMDD_HHMMSS.mp4
```

Generated images are cached in:

```text
temp_slides/fooocus_images/
```

If `Tiếp tục từ bước lỗi` is enabled, valid cached images/audio are reused.
Subtitle cues are cached in:

```text
temp_slides/subtitles.json
```
