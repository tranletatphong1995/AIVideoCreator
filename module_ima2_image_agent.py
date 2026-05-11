"""ima2-gen image provider for the optional ChatGPT online mode."""

import base64
import os
import random
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List
from urllib.parse import urljoin

import requests

from module_ima2_runtime import read_ima2_server_info, resolve_ima2_server_url


class Ima2ImageAgent:
    """Generate illustration images through a running ima2-gen server."""

    IMAGE_DIR = os.path.join("temp_slides", "ima2_images")
    MAX_IMAGE_WORKERS = 2
    RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

    STYLE_HINTS = {
        "modern": "modern technology editorial style, sleek, clean, high contrast",
        "news": "newsroom editorial realism, documentary lighting, credible visual tone",
        "education": "clear educational illustration, friendly explanatory composition",
        "corporate": "premium corporate editorial style, polished, professional",
        "minimal": "minimal editorial composition, restrained, elegant, uncluttered",
        "fantasy": "fantasy atmosphere, magical light, epic and wondrous",
        "science": "scientific visualization, futuristic lab, precise discovery mood",
        "eerie": "eerie mysterious mood, dark atmospheric lighting, tasteful",
        "cinematic": "cinematic film still, dramatic lighting, rich color grading",
        "anime": "anime-inspired cinematic illustration, expressive, vibrant, polished",
        "nature": "natural world, organic textures, beautiful environmental lighting",
        "history": "historical cinematic realism, period details, documentary tone",
    }

    def __init__(
        self,
        server_url: str = "",
        signals=None,
        resolution: tuple = (1280, 720),
        style_preset: str = "modern",
        model_name: str = "gpt-5.4-mini",
        timeout_sec: int = 900,
    ):
        self.server_url = resolve_ima2_server_url(server_url)
        self.signals = signals
        self.width, self.height = resolution
        self.style_preset = style_preset
        self.model_name = model_name or "gpt-5.4-mini"
        self.timeout_sec = timeout_sec
        os.makedirs(self.IMAGE_DIR, exist_ok=True)

    def _log(self, msg: str):
        if self.signals:
            self.signals.log_message.emit(msg)
        try:
            print(msg)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            print(msg.encode(encoding, errors="replace").decode(encoding))

    @staticmethod
    def _is_valid_file(path: str, min_size: int = 1024) -> bool:
        return os.path.exists(path) and os.path.getsize(path) >= min_size

    def _image_size(self) -> str:
        ratio = self.width / max(1, self.height)
        if abs(ratio - 1.0) < 0.08:
            return "1024x1024"
        if ratio < 0.75:
            return "1024x1536"
        if ratio > 1.45:
            return "1536x1024"
        return "1024x1024"

    def _build_prompt(self, slide) -> str:
        image_prompt = str(getattr(slide, "image_prompt", "") or "").strip()
        fallback_visual = str(getattr(slide, "html_idea", "") or "").strip()
        pieces = [
            str(getattr(slide, "title", "")).strip(),
            image_prompt or fallback_visual,
        ]
        subject = ". ".join(part for part in pieces if part)
        subject = re.sub(r"\s+", " ", subject)[:1400]
        return (
            f"{subject}. Create a polished editorial illustration for a video scene. "
            f"Visual style: {self.STYLE_HINTS.get(self.style_preset, self.STYLE_HINTS['modern'])}. "
            "Cinematic composition, clear main subject, rich detail, professional lighting, "
            "safe empty space near the bottom for subtitles. No text, letters, captions, "
            "subtitles, logos, or watermark in the image."
        )

    def _generated_dir(self) -> Path:
        info = read_ima2_server_info()
        storage = info.get("storage") if isinstance(info.get("storage"), dict) else {}
        for key in ("generatedDir", "generated_dir"):
            if storage.get(key):
                return Path(str(storage[key])).expanduser()
        return Path.home() / ".ima2" / "generated"

    def _save_data_url(self, data_url: str, output_path: str) -> str:
        payload = data_url
        if "," in payload:
            payload = payload.split(",", 1)[1]
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(payload))
        return output_path

    def _save_from_filename(self, filename: str, output_path: str) -> str:
        source = self._generated_dir() / filename
        if source.exists():
            shutil.copyfile(source, output_path)
            return output_path

        url = urljoin(self.server_url + "/", f"generated/{filename}")
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(response.content)
        return output_path

    def _save_result(self, data: dict, output_path: str) -> str:
        if isinstance(data.get("image"), str) and data["image"].startswith("data:"):
            return self._save_data_url(data["image"], output_path)

        images = data.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                image = first.get("image")
                if isinstance(image, str) and image.startswith("data:"):
                    return self._save_data_url(image, output_path)
                filename = first.get("filename")
                if isinstance(filename, str):
                    return self._save_from_filename(filename, output_path)

        filename = data.get("filename")
        if isinstance(filename, str):
            return self._save_from_filename(filename, output_path)

        raise RuntimeError(f"ima2 response has no image payload or filename: {data}")

    @staticmethod
    def _retry_after_seconds(response) -> float:
        retry_after = response.headers.get("Retry-After", "")
        if not retry_after:
            return 0.0
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            return 0.0

    def _post_generate_with_retry(self, payload: dict, max_attempts: int = 6):
        last_response = None
        for attempt in range(1, max_attempts + 1):
            response = requests.post(
                f"{self.server_url}/api/generate",
                json=payload,
                timeout=self.timeout_sec,
            )
            if response.status_code == 401:
                raise RuntimeError("ChatGPT OAuth expired. Run: npx @openai/codex login")
            if response.status_code not in self.RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response

            last_response = response
            if attempt >= max_attempts:
                break

            retry_after = self._retry_after_seconds(response)
            backoff = min(90.0, (2 ** (attempt - 1)) * 5.0)
            wait_sec = max(retry_after, backoff) + random.uniform(0.0, 1.5)
            self._log(
                f"   ima2-gen busy/rate-limited ({response.status_code}); "
                f"retry {attempt}/{max_attempts - 1} after {wait_sec:.1f}s"
            )
            time.sleep(wait_sec)

        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError("ima2-gen request failed before receiving a response.")

    def _generate_one(self, slide, output_path: str) -> str:
        payload = {
            "prompt": self._build_prompt(slide),
            "quality": "medium",
            "size": self._image_size(),
            "format": "png",
            "moderation": "low",
            "provider": "oauth",
            "model": self.model_name,
            "n": 1,
            "webSearchEnabled": False,
        }
        response = self._post_generate_with_retry(payload)
        return self._save_result(response.json(), output_path)

    def generate_images_for_plan(self, plan, resume: bool = False, max_workers: int = 1) -> List[str]:
        image_paths = [None] * len(list(getattr(plan, "slides", []) or []))
        slides = list(getattr(plan, "slides", []) or [])
        total = len(slides)
        if total == 0:
            raise RuntimeError("Video plan has no scenes for ima2 image generation.")

        requested_workers = max(1, int(max_workers or 1))
        workers = min(requested_workers, self.MAX_IMAGE_WORKERS)
        if workers < requested_workers:
            self._log(
                f"ima2-gen: limiting image workers from {requested_workers} to {workers} "
                "to avoid API rate limits"
            )
        self._log(f"ima2-gen: generating {total} images through {self.server_url} ({workers} workers)")

        def generate_one(item):
            idx, slide = item
            slide_num = idx + 1
            output_path = os.path.join(self.IMAGE_DIR, f"ima2_slide_{slide_num}.png")
            if resume and self._is_valid_file(output_path):
                self._log(f"   Reusing ima2 image {slide_num}: {output_path}")
                return idx, output_path

            title = str(getattr(slide, "title", f"Scene {slide_num}"))
            self._log(f"   ima2 image {slide_num}/{total}: {title[:80]}")
            result_path = self._generate_one(slide, output_path)
            self._log(f"   Saved image: {output_path}")
            return idx, result_path

        if workers > 1 and total > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(generate_one, item) for item in enumerate(slides)]
                for future in as_completed(futures):
                    idx, path = future.result()
                    image_paths[idx] = path
        else:
            for item in enumerate(slides):
                idx, path = generate_one(item)
                image_paths[idx] = path

        return [path for path in image_paths if path]
