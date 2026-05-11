"""
Fooocus image provider.

This module talks to a running Fooocus-compatible HTTP API and stores one
illustration image per video scene. The app keeps Fooocus as an external image
engine instead of importing its full SDXL codebase into the PyQt process.
"""

import base64
import os
import re
import sys
from typing import List, Optional
from urllib.parse import urljoin

import requests


class FooocusAgent:
    """Generate illustration images for a VideoPlan using a Fooocus API server."""

    IMAGE_DIR = os.path.join("temp_slides", "fooocus_images")

    STYLE_MAP = {
        "modern": ["Fooocus V2", "Fooocus Enhance", "Fooocus Sharp"],
        "news": ["Fooocus V2", "Fooocus Sharp"],
        "education": ["Fooocus V2", "Fooocus Enhance"],
        "corporate": ["Fooocus V2", "Fooocus Sharp"],
        "minimal": ["Fooocus V2"],
        "fantasy": ["Fooocus V2", "Fooocus Enhance", "Fooocus Sharp"],
        "science": ["Fooocus V2", "Fooocus Enhance", "Fooocus Sharp"],
        "eerie": ["Fooocus V2", "Fooocus Enhance", "Fooocus Sharp"],
        "cinematic": ["Fooocus V2", "Fooocus Enhance", "Fooocus Sharp"],
        "anime": ["Fooocus V2", "Fooocus Enhance"],
        "nature": ["Fooocus V2", "Fooocus Enhance", "Fooocus Sharp"],
        "history": ["Fooocus V2", "Fooocus Enhance", "Fooocus Sharp"],
    }

    PROMPT_STYLE_HINTS = {
        "modern": "modern technology editorial style, sleek, clean, high contrast",
        "news": "newsroom editorial realism, documentary lighting, credible visual tone",
        "education": "clear educational illustration, friendly and explanatory composition",
        "corporate": "premium corporate editorial style, polished, professional",
        "minimal": "minimal editorial composition, restrained, elegant, uncluttered",
        "fantasy": "fantasy, mystical atmosphere, magical light, epic and wondrous",
        "science": "scientific visualization, futuristic lab, precise details, discovery mood",
        "eerie": "eerie mysterious mood, dark atmospheric lighting, unsettling but tasteful",
        "cinematic": "cinematic film still, dramatic lighting, rich color grading, wide composition",
        "anime": "anime-inspired cinematic illustration, expressive, vibrant, polished",
        "nature": "natural world, organic textures, beautiful environmental lighting",
        "history": "historical cinematic realism, period details, dramatic documentary tone",
    }

    NEGATIVE_PROMPT = (
        "text, letters, captions, subtitles, watermark, logo, signature, "
        "low quality, blurry, distorted, deformed, bad anatomy, extra fingers"
    )

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8888",
        signals=None,
        resolution: tuple = (1280, 720),
        style_preset: str = "modern",
        timeout_sec: int = 900,
    ):
        self.api_url = (api_url or "http://127.0.0.1:8888").rstrip("/")
        self.signals = signals
        self.width, self.height = resolution
        self.style_preset = style_preset
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

    def _aspect_ratio_selection(self) -> str:
        ratio = self.width / max(1, self.height)
        if abs(ratio - 1.0) < 0.08:
            return "1024*1024"
        if ratio < 0.7:
            return "1024*1792"
        if ratio < 0.9:
            return "1024*1280"
        if ratio > 1.55:
            return "1344*768"
        return "1152*896"

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
            f"Visual style: {self.PROMPT_STYLE_HINTS.get(self.style_preset, self.PROMPT_STYLE_HINTS['modern'])}. "
            "Cinematic composition, clear main subject, rich detail, professional lighting, "
            "safe empty space near the bottom for subtitles. No text, no letters, no captions, "
            "no subtitles, no logos, no watermark in the image."
        )

    def _endpoint(self, path: str) -> str:
        return urljoin(self.api_url + "/", path.lstrip("/"))

    def _check_server(self):
        try:
            requests.get(self.api_url, timeout=10)
        except requests.RequestException as exc:
            raise RuntimeError(
                "Không kết nối được Fooocus API. Hãy chạy Fooocus/Fooocus-API trước, "
                "ví dụ endpoint mặc định http://127.0.0.1:8888."
            ) from exc

    def _save_result_image(self, result, output_path: str) -> str:
        if isinstance(result, dict):
            image_b64 = result.get("base64")
            image_url = result.get("url")
        else:
            image_b64 = None
            image_url = None

        if image_b64:
            if "," in image_b64 and image_b64.strip().startswith("data:"):
                image_b64 = image_b64.split(",", 1)[1]
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(image_b64))
            return output_path

        if image_url:
            if image_url.startswith("/"):
                image_url = self._endpoint(image_url)
            image_response = requests.get(image_url, timeout=120)
            image_response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(image_response.content)
            return output_path

        raise RuntimeError(f"Fooocus response không có base64/url ảnh: {result}")

    def _generate_one(self, slide, output_path: str) -> str:
        payload = {
            "prompt": self._build_prompt(slide),
            "negative_prompt": self.NEGATIVE_PROMPT,
            "style_selections": self.STYLE_MAP.get(self.style_preset, self.STYLE_MAP["modern"]),
            "performance_selection": "Quality",
            "aspect_ratios_selection": self._aspect_ratio_selection(),
            "image_number": 1,
            "image_seed": -1,
            "sharpness": 2.0,
            "guidance_scale": 4.0,
            "require_base64": True,
            "async_process": False,
            "save_extension": "png",
        }

        response = requests.post(
            self._endpoint("/v1/generation/text-to-image"),
            json=payload,
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            result = data[0] if data else None
        elif isinstance(data, dict) and isinstance(data.get("job_result"), list):
            result = data["job_result"][0] if data["job_result"] else None
        else:
            result = data

        if not result:
            raise RuntimeError(f"Fooocus response rỗng: {data}")
        return self._save_result_image(result, output_path)

    def generate_images_for_plan(self, plan, resume: bool = False) -> List[str]:
        """Generate or reuse one PNG illustration per slide."""
        self._check_server()
        image_paths = []
        slides = list(getattr(plan, "slides", []) or [])
        total = len(slides)
        if total == 0:
            raise RuntimeError("Kế hoạch video không có cảnh nào để tạo ảnh Fooocus.")

        self._log(f"🖼️ Fooocus: tạo {total} ảnh minh họa qua {self.api_url}")
        for idx, slide in enumerate(slides, start=1):
            output_path = os.path.join(self.IMAGE_DIR, f"fooocus_slide_{idx}.png")
            if resume and self._is_valid_file(output_path):
                image_paths.append(output_path)
                self._log(f"   🔁 Dùng lại ảnh Fooocus cảnh {idx}: {output_path}")
                continue

            title = str(getattr(slide, "title", f"Cảnh {idx}"))
            self._log(f"   🎨 Fooocus cảnh {idx}/{total}: {title[:80]}")
            image_paths.append(self._generate_one(slide, output_path))
            self._log(f"   ✅ Đã lưu ảnh: {output_path}")

        return image_paths

    def generate_image_for_slide(self, slide, slide_num: int, total_slides: int = 1, resume: bool = False) -> str:
        """Generate or reuse one slide image."""
        self._check_server()
        output_path = os.path.join(self.IMAGE_DIR, f"fooocus_slide_{slide_num}.png")
        if resume and self._is_valid_file(output_path):
            self._log(f"   🔁 Dùng lại ảnh Fooocus cảnh {slide_num}: {output_path}")
            return output_path

        title = str(getattr(slide, "title", f"Cảnh {slide_num}"))
        self._log(f"   🎨 Fooocus cảnh {slide_num}/{total_slides}: {title[:80]}")
        result_path = self._generate_one(slide, output_path)
        self._log(f"   ✅ Đã lưu ảnh: {output_path}")
        return result_path
