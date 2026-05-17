"""
Module 1: Video Agent
- Brainstorm ý tưởng qua Ollama → JSON cấu trúc (Pydantic)
- Generate HTML/CSS composition kiểu HyperFrames cho từng cảnh
- Render HTML/CSS timeline → video clip bằng Playwright headless browser
"""

import os
import json
import re
import sys
import html as html_lib
import time
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from pathlib import Path

from pydantic import BaseModel, Field

from module_ai_providers import LocalOllamaTextProvider


# ══════════════════════════════════════
# Pydantic Models - Cấu trúc dữ liệu
# ══════════════════════════════════════

class SlideContent(BaseModel):
    """Nội dung 1 slide."""
    slide_number: int = Field(description="Số thứ tự slide")
    title: str = Field(description="Tiêu đề slide")
    html_idea: str = Field(description="Mô tả visual và ý chính ngắn gọn để renderer dựng slide an toàn")
    template_id: str = Field(default="", description="Template gợi ý: focus, split, cards, quote")
    visual_type: str = Field(default="", description="Loại visual: abstract, timeline, stats, comparison, quote")
    emphasis: str = Field(default="", description="Sắc thái trình bày: calm, urgent, cinematic, analytical")
    image_prompt: str = Field(default="", description="Prompt ảnh minh họa cho Fooocus, không chứa chữ/subtitle")
    narration: str = Field(description="Lời thoại TTS tiếng Việt cho slide này")
    duration_seconds: int = Field(default=8, description="Thời lượng slide (giây)")
    background_color: str = Field(default="#1a1a2e", description="Màu nền")
    animation_style: str = Field(default="fade-in", description="Kiểu animation CSS")


class VideoPlan(BaseModel):
    """Kế hoạch video tổng thể."""
    title: str = Field(description="Tiêu đề video")
    total_slides: int = Field(description="Tổng số slide")
    slides: List[SlideContent] = Field(description="Danh sách các slide")


# ══════════════════════════════════════
# Video Agent
# ══════════════════════════════════════

class VideoAgent:
    """Agent tạo video từ prompt thông qua Ollama."""

    TEMP_DIR = "temp_slides"
    PREVIEW_DIR = os.path.join(TEMP_DIR, "previews")
    HTML_REELS_DIR = os.path.join(TEMP_DIR, "html_reels_project")
    HTML_CACHE_VERSION = 8
    RENDER_CACHE_VERSION = 10
    STATIC_FRAME_SCALE = 2
    ANIMATED_FRAME_SCALE = 1
    HTML_VIDEO_FPS = 12
    STYLE_PRESETS = {
        "modern": {
            "label": "Công nghệ hiện đại",
            "label_en": "Modern Tech",
            "bg": "#08111f",
            "surface": "#111827",
            "surface2": "#172033",
            "text": "#f8fafc",
            "muted": "#b8c3d9",
            "accent": "#38bdf8",
            "accent2": "#f43f5e",
            "grid": "rgba(56, 189, 248, 0.12)",
        },
        "news": {
            "label": "Bản tin",
            "label_en": "Newsroom",
            "bg": "#f8fafc",
            "surface": "#ffffff",
            "surface2": "#eef2f7",
            "text": "#111827",
            "muted": "#475569",
            "accent": "#dc2626",
            "accent2": "#1d4ed8",
            "grid": "rgba(15, 23, 42, 0.08)",
        },
        "education": {
            "label": "Giáo dục",
            "label_en": "Education",
            "bg": "#102a43",
            "surface": "#183b56",
            "surface2": "#244e6f",
            "text": "#f0f9ff",
            "muted": "#c9e7f2",
            "accent": "#2dd4bf",
            "accent2": "#fbbf24",
            "grid": "rgba(45, 212, 191, 0.11)",
        },
        "corporate": {
            "label": "Doanh nghiệp",
            "label_en": "Corporate",
            "bg": "#f6f8fb",
            "surface": "#ffffff",
            "surface2": "#e9eef6",
            "text": "#172033",
            "muted": "#526173",
            "accent": "#2563eb",
            "accent2": "#14b8a6",
            "grid": "rgba(37, 99, 235, 0.08)",
        },
        "minimal": {
            "label": "Tối giản biên tập",
            "label_en": "Minimal Editorial",
            "bg": "#fbfaf7",
            "surface": "#ffffff",
            "surface2": "#efede7",
            "text": "#1f2933",
            "muted": "#5f6c7b",
            "accent": "#111827",
            "accent2": "#b45309",
            "grid": "rgba(31, 41, 51, 0.07)",
        },
        "fantasy": {
            "label": "Huyền ảo",
            "label_en": "Fantasy",
            "bg": "#151021",
            "surface": "#241a36",
            "surface2": "#32234f",
            "text": "#fff7ed",
            "muted": "#d8c8ff",
            "accent": "#a78bfa",
            "accent2": "#facc15",
            "grid": "rgba(167, 139, 250, 0.10)",
        },
        "science": {
            "label": "Khoa học",
            "label_en": "Science",
            "bg": "#06131a",
            "surface": "#0f2630",
            "surface2": "#163846",
            "text": "#ecfeff",
            "muted": "#a7d8e8",
            "accent": "#22d3ee",
            "accent2": "#84cc16",
            "grid": "rgba(34, 211, 238, 0.12)",
        },
        "eerie": {
            "label": "Ma mị",
            "label_en": "Eerie",
            "bg": "#111114",
            "surface": "#1d1a22",
            "surface2": "#292330",
            "text": "#f5f3ff",
            "muted": "#c7bed8",
            "accent": "#c084fc",
            "accent2": "#ef4444",
            "grid": "rgba(192, 132, 252, 0.09)",
        },
        "cinematic": {
            "label": "Điện ảnh",
            "label_en": "Cinematic",
            "bg": "#12100d",
            "surface": "#201d18",
            "surface2": "#2f2a22",
            "text": "#fff7ed",
            "muted": "#d6c7b7",
            "accent": "#f59e0b",
            "accent2": "#06b6d4",
            "grid": "rgba(245, 158, 11, 0.09)",
        },
        "anime": {
            "label": "Anime",
            "label_en": "Anime",
            "bg": "#101525",
            "surface": "#18223a",
            "surface2": "#233159",
            "text": "#f8fafc",
            "muted": "#c8d5f2",
            "accent": "#fb7185",
            "accent2": "#38bdf8",
            "grid": "rgba(251, 113, 133, 0.10)",
        },
        "nature": {
            "label": "Thiên nhiên",
            "label_en": "Nature",
            "bg": "#102016",
            "surface": "#193524",
            "surface2": "#244b32",
            "text": "#f0fdf4",
            "muted": "#bfdfc7",
            "accent": "#22c55e",
            "accent2": "#fbbf24",
            "grid": "rgba(34, 197, 94, 0.10)",
        },
        "history": {
            "label": "Lịch sử",
            "label_en": "Historical",
            "bg": "#171511",
            "surface": "#29251c",
            "surface2": "#3a3325",
            "text": "#fef3c7",
            "muted": "#d9c9a0",
            "accent": "#d97706",
            "accent2": "#dc2626",
            "grid": "rgba(217, 119, 6, 0.09)",
        },
    }

    def __init__(
        self,
        model_name: str,
        signals=None,
        resolution: tuple = (1280, 720),
        style_preset: str = "modern",
        output_language: str = "vi",
        text_provider=None,
        ai_mode: str = "local",
    ):
        """
        Args:
            model_name: Tên mô hình Ollama (ví dụ: qwen2.5-coder)
            signals: WorkerSignals từ UI để gửi log
            resolution: Tuple (width, height) cho kích thước video
        """
        self.model_name = model_name
        self.ai_mode = ai_mode or "local"
        self.text_provider = text_provider or LocalOllamaTextProvider(model_name)
        self.signals = signals
        self.width, self.height = resolution
        self.style_preset = style_preset if style_preset in self.STYLE_PRESETS else "modern"
        self.output_language = output_language if output_language in {"vi", "en"} else "vi"
        os.makedirs(self.TEMP_DIR, exist_ok=True)
        os.makedirs(self.PREVIEW_DIR, exist_ok=True)

    def _log(self, msg: str):
        """Gửi log an toàn."""
        if self.signals:
            self.signals.log_message.emit(msg)
        try:
            print(msg)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            print(msg.encode(encoding, errors="replace").decode(encoding))

    @staticmethod
    def _is_valid_file(path: str, min_size: int = 1) -> bool:
        return os.path.exists(path) and os.path.getsize(path) >= min_size

    def _render_cache_path(self) -> str:
        return os.path.join(self.TEMP_DIR, "render_cache.json")

    def _html_cache_path(self) -> str:
        return os.path.join(self.TEMP_DIR, "html_cache.json")

    def _html_reels_compositions_dir(self) -> str:
        return os.path.join(self.HTML_REELS_DIR, "compositions")

    def _html_reels_render_path(self) -> str:
        return os.path.join(self.HTML_REELS_DIR, "renders", "html_reels.mp4")

    def _ensure_html_reels_project(self):
        os.makedirs(self._html_reels_compositions_dir(), exist_ok=True)
        os.makedirs(os.path.join(self.HTML_REELS_DIR, "renders"), exist_ok=True)
        package_path = os.path.join(self.HTML_REELS_DIR, "package.json")
        hyperframes_path = os.path.join(self.HTML_REELS_DIR, "hyperframes.json")
        if not os.path.exists(package_path):
            with open(package_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "name": "aivideo-html-reels",
                        "private": True,
                        "type": "module",
                        "scripts": {
                            "check": "npx --yes hyperframes@0.6.12 lint && npx --yes hyperframes@0.6.12 validate",
                            "render": "npx --yes hyperframes@0.6.12 render",
                        },
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        if not os.path.exists(hyperframes_path):
            with open(hyperframes_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                        "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                        "paths": {
                            "blocks": "compositions",
                            "components": "compositions/components",
                            "assets": "assets",
                        },
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

    def _is_html_cache_current(self, slide_count: int) -> bool:
        try:
            with open(self._html_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                data.get("version") == self.HTML_CACHE_VERSION
                and data.get("resolution") == [self.width, self.height]
                and data.get("style_preset") == self.style_preset
                and data.get("output_language") == self.output_language
                and data.get("ai_mode", "local") == self.ai_mode
                and data.get("model_name") == self.model_name
                and data.get("slide_count") == slide_count
            )
        except Exception:
            return False

    def _write_html_cache(self, slide_count: int):
        with open(self._html_cache_path(), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": self.HTML_CACHE_VERSION,
                    "resolution": [self.width, self.height],
                    "style_preset": self.style_preset,
                    "output_language": self.output_language,
                    "ai_mode": self.ai_mode,
                    "model_name": self.model_name,
                    "slide_count": slide_count,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _bitrate_for_size(self, size, intermediate: bool = False) -> str:
        """Pick a high enough bitrate for sharp static text."""
        width, height = size
        pixels = width * height
        if pixels >= 3840 * 2160:
            mbps = 56
        elif pixels >= 2560 * 1440:
            mbps = 34
        elif pixels >= 1920 * 1080:
            mbps = 22
        elif pixels >= 1080 * 1350:
            mbps = 18
        elif pixels >= 1080 * 1080:
            mbps = 16
        else:
            mbps = 10
        if intermediate:
            mbps = int(mbps * 1.25)
        return f"{mbps}M"

    def _ffmpeg_static_frame_params(self) -> list:
        return [
            "-vf", f"scale={self.width}:{self.height}:flags=lanczos",
            "-crf", "14",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ]

    def _static_render_css(self) -> str:
        return f"""
            *, *::before, *::after {{
                box-sizing: border-box !important;
            }}
            html, body {{
                width: {self.width}px !important;
                height: {self.height}px !important;
                margin: 0 !important;
                overflow: hidden !important;
            }}
            html, body, body *, .title, .subtitle {{
                font-family: "Segoe UI", Arial, Tahoma, "Noto Sans", sans-serif !important;
                letter-spacing: 0 !important;
                text-rendering: geometricPrecision;
                -webkit-font-smoothing: antialiased;
                overflow-wrap: anywhere;
                word-break: normal;
            }}
            body:not(:has(#aivc-stage)):not([class*="template-"]) {{
                padding: clamp(28px, 5vmin, 96px) !important;
            }}
            body > * {{
                max-width: 100% !important;
            }}
            body:not(:has(#aivc-stage)):not([class*="template-"]) h1,
            body:not(:has(#aivc-stage)):not([class*="template-"]) .title {{
                max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
                font-size: clamp(32px, min(7vw, 7vh), 92px) !important;
                line-height: 1.08 !important;
            }}
            body:not(:has(#aivc-stage)):not([class*="template-"]) h2,
            body:not(:has(#aivc-stage)):not([class*="template-"]) h3 {{
                max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
                font-size: clamp(24px, min(5vw, 5vh), 64px) !important;
                line-height: 1.15 !important;
            }}
            body:not(:has(#aivc-stage)):not([class*="template-"]) p,
            body:not(:has(#aivc-stage)):not([class*="template-"]) .subtitle,
            body:not(:has(#aivc-stage)):not([class*="template-"]) li {{
                max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
                font-size: clamp(18px, min(3.4vw, 3.4vh), 38px) !important;
                line-height: 1.45 !important;
            }}
            img, video, svg, canvas {{
                max-width: 100% !important;
                max-height: 100% !important;
            }}
        """

    def _prepare_slide_page(self, page, slide_num: int):
        """Run font readiness, text fitting, and DOM QA before screenshot."""
        try:
            page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true")
        except Exception:
            pass
        try:
            page.evaluate("() => window.__aivcPrepareComposition ? window.__aivcPrepareComposition() : true")
        except Exception:
            pass
        try:
            page.evaluate("() => window.__aivcFitSlide ? window.__aivcFitSlide() : true")
        except Exception:
            pass
        time.sleep(0.08)
        qa = self._slide_qa(page)
        if qa and not qa.get("ok"):
            for level in ("compact", "dense", "minimal"):
                try:
                    repaired = page.evaluate(
                        """(level) => {
                            if (window.__aivcRepairSlide) return window.__aivcRepairSlide(level);
                            document.body.classList.add(level);
                            return window.__aivcFitSlide ? window.__aivcFitSlide() : true;
                        }""",
                        level,
                    )
                    time.sleep(0.05)
                    qa = repaired if isinstance(repaired, dict) else self._slide_qa(page)
                    if qa and qa.get("ok"):
                        self._log(f"   QA canh {slide_num}: tu sua bang che do {level}.")
                        break
                except Exception:
                    pass
        if qa and not qa.get("ok"):
            self._log(f"   QA canh {slide_num}: van con {len(qa.get('bad', []))} van de layout nho.")
        elif qa:
            scale = float(qa.get("scale", 1) or 1)
            if scale < 0.72:
                self._log(f"   QA canh {slide_num}: khong tran khung, da scale composition {scale:.2f}x.")
            else:
                self._log(f"   QA canh {slide_num}: khong tran/chong khung.")

    def _seek_slide_page(self, page, seconds: float):
        """Seek a HyperFrames-style composition to a deterministic timestamp."""
        try:
            page.evaluate(
                """(seconds) => {
                    if (window.__aivcSeek) return window.__aivcSeek(seconds);
                    if (window.__timelines) {
                        Object.values(window.__timelines).forEach((tl) => {
                            if (!tl) return;
                            if (typeof tl.pause === "function") tl.pause();
                            if (typeof tl.time === "function") tl.time(seconds, false);
                            else if (typeof tl.seek === "function") tl.seek(seconds, false);
                        });
                    }
                    document.querySelectorAll(".clip,[data-start]").forEach((el) => {
                        const start = Number.parseFloat(el.dataset.start || "0") || 0;
                        const rawDuration = el.dataset.duration || "999999";
                        const duration = rawDuration === "full" ? 999999 : (Number.parseFloat(rawDuration) || 999999);
                        const visible = seconds >= start && seconds <= start + duration;
                        el.style.visibility = visible ? "visible" : "hidden";
                        el.style.pointerEvents = visible ? "" : "none";
                    });
                    return true;
                }""",
                float(seconds),
            )
        except Exception:
            pass

    def _slide_qa(self, page) -> Optional[dict]:
        try:
            return page.evaluate(
                """() => {
                    if (window.__aivcQaSlide) return window.__aivcQaSlide();
                    const vw = window.innerWidth;
                    const vh = window.innerHeight;
                    const bad = [];
                    const stage = document.querySelector("[data-composition-id]");
                    if (stage && (Number(stage.dataset.width) !== vw || Number(stage.dataset.height) !== vh)) {
                        bad.push({type: "composition-size", width: stage.dataset.width, height: stage.dataset.height});
                    }
                    if (document.documentElement.scrollWidth > vw + 1 || document.documentElement.scrollHeight > vh + 1) {
                        bad.push({type: "page-scroll"});
                    }
                    document.querySelectorAll("body *").forEach((el) => {
                        const rect = el.getBoundingClientRect();
                        if (!rect.width || !rect.height) return;
                        if (rect.left < -1 || rect.top < -1 || rect.right > vw + 1 || rect.bottom > vh + 1) {
                            bad.push({type: "bounds", name: el.tagName.toLowerCase()});
                        }
                        const style = getComputedStyle(el);
                        if (el.matches("[data-fit]") && style.overflow !== "visible" && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)) {
                            bad.push({type: "overflow", name: el.tagName.toLowerCase()});
                        }
                    });
                    return {ok: bad.length === 0, bad: bad.slice(0, 8)};
                }"""
            )
        except Exception:
            return None

    def _write_static_frame_video(self, frame_path: str, output_path: str, duration: int) -> bool:
        clip = None
        try:
            from moviepy import ImageClip

            clip = ImageClip(frame_path).with_duration(duration).with_fps(30)
            clip.write_videofile(
                output_path,
                codec="libx264",
                audio=False,
                fps=30,
                logger=None,
                threads=4,
                preset="slow",
                bitrate=self._bitrate_for_size((self.width, self.height), intermediate=True),
                ffmpeg_params=self._ffmpeg_static_frame_params(),
            )
            return True
        except Exception as e:
            self._log(f"   ❌ Lỗi tạo video tĩnh từ frame: {e}")
            return False
        finally:
            if clip:
                try:
                    clip.close()
                except Exception:
                    pass

    def _write_frame_sequence_video(self, frame_paths: List[str], output_path: str, fps: int) -> bool:
        clip = None
        try:
            from moviepy import ImageSequenceClip

            if not frame_paths:
                raise ValueError("Khong co frame nao de encode")
            clip = ImageSequenceClip(frame_paths, fps=fps)
            clip.write_videofile(
                output_path,
                codec="libx264",
                audio=False,
                fps=fps,
                logger=None,
                threads=4,
                preset="medium",
                bitrate=self._bitrate_for_size((self.width, self.height), intermediate=True),
                ffmpeg_params=self._ffmpeg_static_frame_params(),
            )
            return True
        except Exception as e:
            self._log(f"   ❌ Lỗi tạo video HTML/CSS từ frame sequence: {e}")
            return False
        finally:
            if clip:
                try:
                    clip.close()
                except Exception:
                    pass

    def _is_render_cache_current(self, html_files: List[str]) -> bool:
        try:
            with open(self._render_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                data.get("version") == self.RENDER_CACHE_VERSION
                and data.get("resolution") == [self.width, self.height]
                and data.get("style_preset") == self.style_preset
                and data.get("output_language") == self.output_language
                and data.get("ai_mode", "local") == self.ai_mode
                and data.get("model_name") == self.model_name
                and data.get("slide_count") == len(html_files)
            )
        except Exception:
            return False

    def _write_render_cache(self, slide_count: int):
        with open(self._render_cache_path(), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": self.RENDER_CACHE_VERSION,
                    "resolution": [self.width, self.height],
                    "style_preset": self.style_preset,
                    "output_language": self.output_language,
                    "ai_mode": self.ai_mode,
                    "model_name": self.model_name,
                    "slide_count": slide_count,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ──────────────────────────────────────
    # Giai đoạn 1: Brainstorming
    # ──────────────────────────────────────
    def brainstorm(self, user_prompt: str, max_slides: int = 5) -> VideoPlan:
        """
        Gửi prompt cho Ollama để tạo kế hoạch video dạng JSON.
        Dùng Pydantic để validate & ép kiểu.
        """
        self._log(f"🧠 Đang brainstorm với mô hình: {self.model_name}")
        self._log(f"📝 Prompt: {user_prompt[:100]}...")
        language_rules = self._language_rules()
        language_name = self._language_name()

        system_prompt = f"""Bạn là một nhà thiết kế video chuyên nghiệp. 
Nhiệm vụ: Phân tích ý tưởng của người dùng và tạo kế hoạch video gồm tối đa {max_slides} slides.
Ngôn ngữ đầu ra bắt buộc: {language_name}.

Trả lời ĐÚNG định dạng JSON (không markdown, không giải thích thêm):
{{
    "title": "Tiêu đề video",
    "total_slides": <số>,
    "slides": [
        {{
            "slide_number": 1,
            "title": "Tiêu đề slide 1",
            "html_idea": "Mô tả visual và 1-3 ý chính ngắn gọn, không nhồi nhiều chữ",
            "template_id": "focus|split|cards|quote",
            "visual_type": "abstract|timeline|stats|comparison|quote",
            "emphasis": "calm|urgent|cinematic|analytical",
            "image_prompt": "Prompt tiếng Anh mô tả ảnh minh họa cho Fooocus/SDXL, chỉ hình ảnh, không chữ, không subtitle, không logo",
            "narration": "Lời thuyết minh tiếng Việt cho slide này (2-4 câu, tự nhiên)",
            "duration_seconds": 8,
            "background_color": "#1a1a2e",
            "animation_style": "none"
        }}
    ]
}}

Quy tắc:
- Mỗi slide phải có narration đúng ngôn ngữ đầu ra, tự nhiên, dễ nghe
{language_rules}
- animation_style mô tả motion ngắn: fade, pop, sweep, pulse, counter, reveal
- Mỗi slide nên có duration_seconds từ 6-12 giây
- html_idea mô tả visual và ý chính thật ngắn gọn; không nhồi nhiều chữ vì app sẽ tự dựng layout an toàn
- template_id chỉ chọn một trong: focus, split, cards, quote. Với video dọc ưu tiên focus/split/quote.
- visual_type chỉ chọn một trong: abstract, timeline, stats, comparison, quote. Chọn theo nội dung, không để tất cả giống nhau.
- emphasis chỉ chọn một trong: calm, urgent, cinematic, analytical.
- image_prompt dùng riêng cho Fooocus tạo ảnh minh họa theo chủ đề/cảnh; viết bằng tiếng Anh mô tả cảnh, ánh sáng, nhân vật/vật thể, mood, bố cục
- image_prompt tuyệt đối KHÔNG yêu cầu chữ trong ảnh: no text, no captions, no subtitle, no watermark, no logo
"""

        try:
            response = self.text_provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                options={"temperature": 0.7, "num_predict": 4096}
            )

            raw_text = response["message"]["content"]
            self._log(f"📨 Nhận được phản hồi ({len(raw_text)} ký tự)")

            # Trích xuất JSON từ phản hồi
            json_data = self._extract_json(raw_text)
            plan = VideoPlan(**json_data)

            self._log(f"✅ Kế hoạch: '{plan.title}' - {plan.total_slides} cảnh")
            for s in plan.slides:
                self._log(f"   📄 Cảnh {s.slide_number}: {s.title} ({s.duration_seconds}s)")

            return plan

        except Exception as e:
            self._log(f"❌ Lỗi brainstorm: {e}")
            self._log("🔄 Tạo kế hoạch mặc định...")
            return self._fallback_plan(user_prompt, max_slides)

    def _extract_json(self, text: str) -> dict:
        """Trích xuất JSON từ văn bản (có thể bọc trong ```json ... ```)."""
        # Thử tìm block JSON
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{.*\})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # Thử parse toàn bộ text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ValueError(f"Không thể trích xuất JSON từ phản hồi")

    def _fallback_plan(self, prompt: str, max_slides: int) -> VideoPlan:
        """Kế hoạch dự phòng nếu LLM không trả về JSON hợp lệ."""
        slides = []
        for i in range(min(3, max_slides)):
            if self.output_language == "en":
                title = f"Part {i + 1}"
                html_idea = f"A clean editorial slide with a large title and key content about: {prompt[:50]}"
                image_prompt = f"Editorial cinematic illustration about {prompt[:90]}, clear subject, professional lighting, no text, no captions, no watermark"
                narration = f"This is part {i + 1} of our video about {prompt[:80]}."
            else:
                title = f"Phần {i + 1}"
                html_idea = f"Slide biên tập rõ ràng với tiêu đề lớn và nội dung chính về: {prompt[:50]}"
                image_prompt = f"Editorial cinematic illustration about {prompt[:90]}, clear subject, professional lighting, no text, no captions, no watermark"
                narration = f"Đây là phần {i + 1} trong video của chúng ta về {prompt[:80]}."
            slides.append(SlideContent(
                slide_number=i + 1,
                title=title,
                html_idea=html_idea,
                template_id=["focus", "split", "quote"][i % 3],
                visual_type=["abstract", "timeline", "stats"][i % 3],
                emphasis="calm",
                image_prompt=image_prompt,
                narration=narration,
                duration_seconds=8,
                background_color=["#1a1a2e", "#0f3460", "#16213e"][i % 3],
                animation_style="none"
            ))
        return VideoPlan(
            title=f"Video: {prompt[:50]}",
            total_slides=len(slides),
            slides=slides
        )

    # ──────────────────────────────────────
    # Giai đoạn 2: Generate HTML/CSS
    # ──────────────────────────────────────
    def _preset(self) -> dict:
        return self.STYLE_PRESETS.get(self.style_preset, self.STYLE_PRESETS["modern"])

    def _language_name(self) -> str:
        return "tiếng Việt" if self.output_language == "vi" else "English"

    def _language_rules(self) -> str:
        if self.output_language == "en":
            return (
                "- All visible slide text, titles, labels, and narration must be in English.\n"
                "- Do not mix Vietnamese into the generated video content unless it is a proper noun."
            )
        return (
            "- Toàn bộ chữ hiển thị trong video, tiêu đề, nhãn và lời thuyết minh phải viết bằng tiếng Việt tự nhiên.\n"
            "- Không dùng tiếng Anh trong nội dung video, trừ tên riêng, thuật ngữ bắt buộc hoặc thương hiệu."
        )

    def _ui_text(self, vi: str, en: str) -> str:
        return vi if self.output_language == "vi" else en

    def _legacy_slide_points(self, text: str, max_points: int = 3) -> List[str]:
        chunks = [
            part.strip(" -•\t\r\n")
            for part in re.split(r"[.;:\n]+", text or "")
            if part.strip(" -•\t\r\n")
        ]
        if not chunks and text:
            chunks = [text.strip()]
        points = []
        for chunk in chunks:
            if len(chunk) > 115:
                chunk = chunk[:112].rstrip() + "..."
            points.append(chunk)
            if len(points) >= max_points:
                break
        while len(points) < max_points:
            points.append(self._ui_text("Ý chính được trình bày rõ ràng, dễ theo dõi.", "A clear key point presented for easy viewing."))
        return points

    def _legacy_template_html(self, slide: SlideContent) -> str:
        preset = self._preset()
        title = html_lib.escape(slide.title)
        idea = html_lib.escape(slide.html_idea[:260])
        points = [html_lib.escape(point) for point in self._slide_points(slide.html_idea)]
        label = html_lib.escape(self._ui_text(preset["label"], preset.get("label_en", preset["label"])))
        layout = ["hero", "split", "cards", "statement"][(slide.slide_number - 1) % 4]
        aspect_class = "portrait" if self.height > self.width else "landscape"
        html_lang = "vi" if self.output_language == "vi" else "en"

        if layout == "hero":
            content = f"""
    <main class="slide-shell layout-hero">
        <section class="copy">
            <div class="eyebrow">{label}</div>
            <h1>{title}</h1>
            <p class="lead">{idea}</p>
        </section>
        <section class="side-panel">
            <div class="metric">{html_lib.escape(self._ui_text("Trọng tâm", "Focus"))}</div>
            <div class="metric-label">{html_lib.escape(self._ui_text("Ý chính", "Key point"))}</div>
            <div class="rule"></div>
            <p>{points[0]}</p>
        </section>
    </main>"""
        elif layout == "split":
            content = f"""
    <main class="slide-shell layout-split">
        <section class="copy">
            <div class="eyebrow">{label}</div>
            <h1>{title}</h1>
            <p class="lead">{points[0]}</p>
        </section>
        <section class="stack">
            <article><p>{points[0]}</p></article>
            <article><p>{points[1]}</p></article>
            <article><p>{points[2]}</p></article>
        </section>
    </main>"""
        elif layout == "cards":
            content = f"""
    <main class="slide-shell layout-cards">
        <section class="copy">
            <div class="eyebrow">{label}</div>
            <h1>{title}</h1>
        </section>
        <section class="card-grid">
            <article><p>{points[0]}</p></article>
            <article><p>{points[1]}</p></article>
            <article><p>{points[2]}</p></article>
        </section>
    </main>"""
        else:
            content = f"""
    <main class="slide-shell layout-statement">
        <section class="copy">
            <div class="eyebrow">{label}</div>
            <h1>{title}</h1>
            <p class="lead">{idea}</p>
        </section>
        <section class="statement-list">
            <p>{points[0]}</p>
            <p>{points[1]}</p>
        </section>
    </main>"""

        return f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={self.width}, height={self.height}, initial-scale=1.0">
    <style>
        :root {{
            --bg: {preset["bg"]};
            --surface: {preset["surface"]};
            --surface2: {preset["surface2"]};
            --text: {preset["text"]};
            --muted: {preset["muted"]};
            --accent: {preset["accent"]};
            --accent2: {preset["accent2"]};
            --grid: {preset["grid"]};
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html, body {{
            width: {self.width}px;
            height: {self.height}px;
            overflow: hidden;
        }}
        body {{
            color: var(--text);
            font-family: "Segoe UI", Arial, Tahoma, "Noto Sans", sans-serif;
            background:
                linear-gradient(90deg, var(--grid) 1px, transparent 1px),
                linear-gradient(0deg, var(--grid) 1px, transparent 1px),
                radial-gradient(circle at 82% 16%, color-mix(in srgb, var(--accent) 26%, transparent), transparent 30%),
                linear-gradient(135deg, var(--bg), color-mix(in srgb, var(--bg) 78%, var(--surface2)));
            background-size: 88px 88px, 88px 88px, auto, auto;
            padding: clamp(40px, 5.5vmin, 88px);
            text-rendering: geometricPrecision;
            -webkit-font-smoothing: antialiased;
        }}
        .slide-shell {{
            width: 100%;
            height: 100%;
            display: grid;
            gap: clamp(22px, 4vmin, 56px);
            align-items: center;
        }}
        .eyebrow {{
            color: var(--accent);
            font-size: clamp(14px, 1.8vmin, 22px);
            font-weight: 800;
            letter-spacing: 0;
            margin-bottom: clamp(14px, 2vmin, 26px);
            text-transform: uppercase;
        }}
        h1 {{
            max-width: 980px;
            font-size: clamp(42px, min(7vw, 7vh), 104px);
            line-height: 1.02;
            font-weight: 900;
            letter-spacing: 0;
        }}
        .lead {{
            max-width: 940px;
            margin-top: clamp(18px, 2.5vmin, 34px);
            color: var(--muted);
            font-size: clamp(22px, min(3.2vw, 3.2vh), 40px);
            line-height: 1.35;
            font-weight: 520;
        }}
        .layout-hero, .layout-split {{
            grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.8fr);
        }}
        .layout-cards, .layout-statement {{
            grid-template-rows: auto 1fr;
        }}
        .side-panel, .stack article, .card-grid article, .statement-list {{
            background: color-mix(in srgb, var(--surface) 92%, transparent);
            border: 1px solid color-mix(in srgb, var(--accent) 22%, transparent);
            border-radius: 8px;
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.20);
        }}
        .side-panel {{
            padding: clamp(28px, 4vmin, 52px);
        }}
        .metric {{
            color: var(--accent2);
            font-size: clamp(34px, 5.4vmin, 72px);
            line-height: 1.02;
            font-weight: 900;
        }}
        .metric-label, .side-panel p {{
            color: var(--muted);
            font-size: clamp(18px, 2.4vmin, 30px);
            line-height: 1.35;
        }}
        .rule {{
            height: 3px;
            width: 42%;
            margin: clamp(24px, 4vmin, 42px) 0;
            background: linear-gradient(90deg, var(--accent), var(--accent2));
        }}
        .stack {{
            display: grid;
            gap: clamp(14px, 2vmin, 24px);
        }}
        .stack article {{
            display: grid;
            border-left: 4px solid var(--accent2);
            padding: clamp(20px, 2.8vmin, 36px);
            align-items: start;
        }}
        .stack p, .card-grid p, .statement-list p {{
            color: var(--text);
            font-size: clamp(19px, min(2.5vw, 2.5vh), 32px);
            line-height: 1.34;
            font-weight: 580;
        }}
        .card-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: clamp(16px, 2.5vmin, 30px);
            align-self: stretch;
        }}
        .card-grid article {{
            padding: clamp(24px, 3.2vmin, 42px);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 260px;
        }}
        .statement-list {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: clamp(18px, 3vmin, 34px);
            padding: clamp(26px, 4vmin, 52px);
        }}
        .portrait .layout-hero,
        .portrait .layout-split,
        .portrait .statement-list,
        .portrait .card-grid {{
            grid-template-columns: 1fr;
        }}
        .portrait .card-grid {{
            grid-template-rows: repeat(3, minmax(0, 1fr));
        }}
        .portrait .card-grid article {{
            min-height: 0;
        }}
    </style>
</head>
<body class="{aspect_class}">
{content}
</body>
</html>"""

    def _text_budget(self) -> dict:
        ratio = self.width / max(1, self.height)
        if ratio < 0.8:
            return {"title": 46, "lead": 118, "point": 58, "points": 2}
        if ratio > 1.35:
            return {"title": 62, "lead": 154, "point": 76, "points": 3}
        return {"title": 52, "lead": 130, "point": 66, "points": 3}

    def _shorten_text(self, text: str, limit: int) -> str:
        clean = re.sub(r"\s+", " ", (text or "").strip())
        if len(clean) <= limit:
            return clean
        clipped = clean[: max(0, limit - 3)].rstrip()
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        return clipped.rstrip(" .,!?:;") + "..."

    def _slide_points(self, text: str, max_points: Optional[int] = None) -> List[str]:
        budget = self._text_budget()
        max_points = max_points or budget["points"]
        chunks = [
            part.strip(" -\t\r\n")
            for part in re.split(r"[.;:\n]+", text or "")
            if part.strip(" -\t\r\n")
        ]
        if not chunks and text:
            chunks = [text.strip()]
        points = []
        seen = set()
        for chunk in chunks:
            point = self._shorten_text(chunk, budget["point"])
            key = point.lower()
            if key and key not in seen:
                points.append(point)
                seen.add(key)
            if len(points) >= max_points:
                break
        fallback = self._ui_text(
            "Y chinh duoc trinh bay ro rang, de theo doi.",
            "A clear key point presented for easy viewing.",
        )
        while len(points) < max_points:
            points.append(fallback)
        return points

    def _aspect_class(self) -> str:
        ratio = self.width / max(1, self.height)
        if ratio < 0.8:
            return "portrait"
        if ratio > 1.25:
            return "landscape"
        return "square"

    def _template_kind(self, slide: SlideContent) -> str:
        requested = (getattr(slide, "template_id", "") or "").strip().lower()
        allowed = {"focus", "split", "cards", "quote"}
        if requested in allowed:
            if self._aspect_class() == "portrait" and requested == "cards":
                return "split"
            return requested

        aspect = self._aspect_class()
        if aspect == "portrait":
            return ["focus", "split", "quote"][(slide.slide_number - 1) % 3]
        if aspect == "square":
            return ["focus", "cards", "quote"][(slide.slide_number - 1) % 3]
        return ["focus", "split", "cards", "quote"][(slide.slide_number - 1) % 4]

    def _visual_type(self, slide: SlideContent) -> str:
        requested = (getattr(slide, "visual_type", "") or "").strip().lower()
        allowed = {"abstract", "timeline", "stats", "comparison", "quote"}
        if requested in allowed:
            return requested
        text = f"{slide.title} {slide.html_idea}".lower()
        if any(word in text for word in ["timeline", "lịch sử", "giai đoạn", "hành trình", "quá trình", "evolution"]):
            return "timeline"
        if any(word in text for word in ["số", "%", "tăng", "giảm", "metric", "kpi", "thống kê", "data"]):
            return "stats"
        if any(word in text for word in ["vs", "so sánh", "khác biệt", "trước", "sau", "compare"]):
            return "comparison"
        if self._template_kind(slide) == "quote":
            return "quote"
        return "abstract"

    def _fit_runtime_js(self) -> str:
        return """
        (() => {
            const px = (value, fallback) => {
                const parsed = Number.parseFloat(value);
                return Number.isFinite(parsed) ? parsed : fallback;
            };
            const overflows = (el) => (
                el.scrollHeight > el.clientHeight + 1 ||
                el.scrollWidth > el.clientWidth + 1
            );
            const fitOne = (el) => {
                const style = getComputedStyle(el);
                const max = px(el.dataset.max, px(style.fontSize, 32));
                const min = px(el.dataset.min, Math.max(13, max * 0.52));
                const original = el.dataset.originalText || el.textContent || "";
                el.dataset.originalText = original;
                el.textContent = original;
                let low = min;
                let high = max;
                for (let i = 0; i < 18; i += 1) {
                    const mid = (low + high) / 2;
                    el.style.fontSize = `${mid}px`;
                    if (overflows(el)) high = mid;
                    else low = mid;
                }
                el.style.fontSize = `${Math.floor(low * 10) / 10}px`;
                if (!overflows(el)) return;
                const words = original.split(/\\s+/).filter(Boolean);
                let left = 1;
                let right = words.length;
                while (left < right) {
                    const mid = Math.ceil((left + right) / 2);
                    el.textContent = `${words.slice(0, mid).join(" ").replace(/[\\s.,!?:;]+$/, "")}...`;
                    if (overflows(el)) right = mid - 1;
                    else left = mid;
                }
                el.textContent = `${words.slice(0, Math.max(1, left)).join(" ").replace(/[\\s.,!?:;]+$/, "")}...`;
            };
            const qa = () => {
                const vw = window.innerWidth;
                const vh = window.innerHeight;
                const bad = [];
                const stage = document.querySelector("[data-composition-id]");
                if (stage && (Number(stage.dataset.width) !== vw || Number(stage.dataset.height) !== vh)) {
                    bad.push({type: "composition-size", width: stage.dataset.width, height: stage.dataset.height});
                }
                if (document.documentElement.scrollWidth > vw + 1 || document.documentElement.scrollHeight > vh + 1) {
                    bad.push({type: "page-scroll", w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight});
                }
                document.querySelectorAll("body *").forEach((el) => {
                    const rect = el.getBoundingClientRect();
                    if (!rect.width || !rect.height) return;
                    const style = getComputedStyle(el);
                    const tag = el.tagName.toLowerCase();
                    const cls = el.className && typeof el.className === "string" ? el.className.split(/\\s+/).slice(0, 2).join(".") : "";
                    const name = cls ? `${tag}.${cls}` : tag;
                    if (rect.left < -1 || rect.top < -1 || rect.right > vw + 1 || rect.bottom > vh + 1) {
                        bad.push({type: "bounds", name, left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom});
                    }
                    if (el.matches("[data-fit]") && style.overflow !== "visible" && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)) {
                        bad.push({type: "overflow", name, sw: el.scrollWidth, sh: el.scrollHeight, cw: el.clientWidth, ch: el.clientHeight});
                    }
                });
                return {ok: bad.length === 0, bad: bad.slice(0, 8)};
            };
            window.__aivcFitSlide = () => {
                document.querySelectorAll("[data-fit]").forEach(fitOne);
                return true;
            };
            window.__aivcQaSlide = qa;
            window.__aivcRepairSlide = (level = "compact") => {
                document.body.classList.add(level);
                window.__aivcFitSlide();
                return qa();
            };
            window.__aivcFitSlide();
        })();
        """

    def _visual_html(self, visual_type: str, points: List[str]) -> str:
        safe_points = [html_lib.escape(self._shorten_text(point, 42)) for point in points[:3]]
        while len(safe_points) < 3:
            safe_points.append("")
        if visual_type == "timeline":
            return f"""
            <div class="timeline-visual" data-block="visual.timeline" data-start="0" data-duration="full" data-track-index="1">
                <div><span></span><p>{safe_points[0]}</p></div>
                <div><span></span><p>{safe_points[1]}</p></div>
                <div><span></span><p>{safe_points[2]}</p></div>
            </div>
        """
        if visual_type == "stats":
            return f"""
            <div class="stats-visual" data-block="visual.stats" data-start="0" data-duration="full" data-track-index="1">
                <div><strong>01</strong><p>{safe_points[0]}</p></div>
                <div><strong>02</strong><p>{safe_points[1]}</p></div>
                <div><strong>03</strong><p>{safe_points[2]}</p></div>
            </div>
        """
        if visual_type == "comparison":
            return f"""
            <div class="compare-visual" data-block="visual.comparison" data-start="0" data-duration="full" data-track-index="1">
                <div><strong>A</strong><p>{safe_points[0]}</p></div>
                <div><strong>B</strong><p>{safe_points[1]}</p></div>
            </div>
        """
        if visual_type == "quote":
            return f"""
            <div class="quote-mark" data-block="visual.quote" data-start="0" data-duration="full" data-track-index="1">“</div>
        """
        return """
            <div class="orb one"></div>
            <div class="orb two"></div>
            <div class="diagram" data-block="visual.abstract" data-start="0" data-duration="full" data-track-index="1"><span></span><span></span><span></span><span></span></div>
            <div class="signal-ring"></div>
        """

    def _template_html(self, slide: SlideContent) -> str:
        preset = self._preset()
        budget = self._text_budget()
        title = html_lib.escape(self._shorten_text(slide.title, budget["title"]))
        lead = html_lib.escape(self._shorten_text(slide.html_idea, budget["lead"]))
        point_texts = self._slide_points(slide.html_idea, budget["points"])
        points = [html_lib.escape(point) for point in point_texts]
        while len(points) < 3:
            points.append(points[-1] if points else "")
        label = html_lib.escape(self._ui_text(preset["label"], preset.get("label_en", preset["label"])))
        focus_label = html_lib.escape(self._ui_text("Trong tam", "Focus"))
        html_lang = "vi" if self.output_language == "vi" else "en"
        aspect_class = self._aspect_class()
        template_kind = self._template_kind(slide)
        visual_type = self._visual_type(slide)
        visual = self._visual_html(visual_type, point_texts)
        duration = max(1, int(getattr(slide, "duration_seconds", 8) or 8))

        if template_kind == "focus":
            content = f"""
    <main class="safe-frame template-focus" data-composition-id="slide-{slide.slide_number}" data-width="{self.width}" data-height="{self.height}" data-duration="{duration}">
        <section class="copy-zone">
            <div class="eyebrow" data-block="label" data-start="0" data-duration="full" data-track-index="2">{label}</div>
            <h1 class="fit-title" data-fit data-block="title" data-start="0" data-duration="full" data-track-index="3" data-min="30" data-max="96">{title}</h1>
            <p class="fit-lead" data-fit data-block="lead" data-start="0" data-duration="full" data-track-index="4" data-min="17" data-max="38">{lead}</p>
        </section>
        <section class="visual-card {visual_type}" data-block="visual-card" data-start="0" data-duration="full" data-track-index="1">
            {visual}
            <div class="focus-chip">{focus_label}</div>
            <p class="fit-point featured" data-fit data-min="16" data-max="30">{points[0]}</p>
        </section>
    </main>"""
        elif template_kind == "split":
            content = f"""
    <main class="safe-frame template-split" data-composition-id="slide-{slide.slide_number}" data-width="{self.width}" data-height="{self.height}" data-duration="{duration}">
        <section class="visual-card wide {visual_type}" data-block="visual-card" data-start="0" data-duration="full" data-track-index="1">{visual}</section>
        <section class="copy-zone">
            <div class="eyebrow" data-block="label" data-start="0" data-duration="full" data-track-index="2">{label}</div>
            <h1 class="fit-title compact-title" data-fit data-block="title" data-start="0" data-duration="full" data-track-index="3" data-min="28" data-max="82">{title}</h1>
            <div class="point-stack">
                <p class="fit-point" data-fit data-block="point" data-start="0" data-duration="full" data-track-index="4" data-min="15" data-max="30">{points[0]}</p>
                <p class="fit-point" data-fit data-block="point" data-start="0" data-duration="full" data-track-index="5" data-min="15" data-max="30">{points[1]}</p>
                <p class="fit-point" data-fit data-block="point" data-start="0" data-duration="full" data-track-index="6" data-min="15" data-max="30">{points[2]}</p>
            </div>
        </section>
    </main>"""
        elif template_kind == "cards":
            content = f"""
    <main class="safe-frame template-cards" data-composition-id="slide-{slide.slide_number}" data-width="{self.width}" data-height="{self.height}" data-duration="{duration}">
        <section class="copy-zone top-copy">
            <div class="eyebrow" data-block="label" data-start="0" data-duration="full" data-track-index="1">{label}</div>
            <h1 class="fit-title compact-title" data-fit data-block="title" data-start="0" data-duration="full" data-track-index="2" data-min="28" data-max="78">{title}</h1>
        </section>
        <section class="card-grid">
            <article data-block="card" data-start="0" data-duration="full" data-track-index="3"><p class="fit-point" data-fit data-min="15" data-max="30">{points[0]}</p></article>
            <article data-block="card" data-start="0" data-duration="full" data-track-index="4"><p class="fit-point" data-fit data-min="15" data-max="30">{points[1]}</p></article>
            <article data-block="card" data-start="0" data-duration="full" data-track-index="5"><p class="fit-point" data-fit data-min="15" data-max="30">{points[2]}</p></article>
        </section>
    </main>"""
        else:
            content = f"""
    <main class="safe-frame template-quote" data-composition-id="slide-{slide.slide_number}" data-width="{self.width}" data-height="{self.height}" data-duration="{duration}">
        <section class="quote-copy">
            <div class="eyebrow" data-block="label" data-start="0" data-duration="full" data-track-index="1">{label}</div>
            <h1 class="fit-title quote-title" data-fit data-block="title" data-start="0" data-duration="full" data-track-index="2" data-min="30" data-max="96">{title}</h1>
            <p class="fit-lead quote-lead" data-fit data-block="lead" data-start="0" data-duration="full" data-track-index="3" data-min="17" data-max="36">{lead}</p>
        </section>
        <section class="statement-row">
            <p class="fit-point" data-fit data-block="point" data-start="0" data-duration="full" data-track-index="4" data-min="15" data-max="30">{points[0]}</p>
            <p class="fit-point" data-fit data-block="point" data-start="0" data-duration="full" data-track-index="5" data-min="15" data-max="30">{points[1]}</p>
        </section>
    </main>"""

        return f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={self.width}, height={self.height}, initial-scale=1.0">
    <style>
        :root {{
            --bg: {preset["bg"]};
            --surface: {preset["surface"]};
            --surface2: {preset["surface2"]};
            --text: {preset["text"]};
            --muted: {preset["muted"]};
            --accent: {preset["accent"]};
            --accent2: {preset["accent2"]};
            --grid: {preset["grid"]};
            --pad: clamp(34px, 5.2vmin, 92px);
            --gap: clamp(18px, 3.2vmin, 52px);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html, body {{
            width: {self.width}px;
            height: {self.height}px;
            overflow: hidden;
        }}
        body {{
            color: var(--text);
            font-family: "Segoe UI", Arial, Tahoma, "Noto Sans", sans-serif;
            background:
                linear-gradient(90deg, var(--grid) 1px, transparent 1px),
                linear-gradient(0deg, var(--grid) 1px, transparent 1px),
                radial-gradient(circle at 84% 12%, color-mix(in srgb, var(--accent) 24%, transparent), transparent 30%),
                linear-gradient(135deg, var(--bg), color-mix(in srgb, var(--bg) 76%, var(--surface2)));
            background-size: 88px 88px, 88px 88px, auto, auto;
            padding: var(--pad);
            text-rendering: geometricPrecision;
            -webkit-font-smoothing: antialiased;
        }}
        .safe-frame {{
            width: 100%;
            height: 100%;
            display: grid;
            gap: var(--gap);
            overflow: hidden;
        }}
        .template-focus {{
            grid-template-columns: minmax(0, 1.12fr) minmax(300px, 0.88fr);
            align-items: stretch;
        }}
        .template-split {{
            grid-template-columns: minmax(300px, 0.92fr) minmax(0, 1.08fr);
            align-items: stretch;
        }}
        .template-cards {{
            grid-template-rows: minmax(170px, 0.42fr) minmax(0, 0.58fr);
        }}
        .template-quote {{
            grid-template-rows: minmax(0, 1fr) minmax(120px, 0.28fr);
            align-items: center;
        }}
        .copy-zone, .quote-copy {{
            min-width: 0;
            min-height: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
            overflow: hidden;
        }}
        .top-copy {{ justify-content: end; }}
        .eyebrow {{
            flex: 0 0 auto;
            color: var(--accent);
            font-size: clamp(13px, 1.55vmin, 22px);
            font-weight: 820;
            letter-spacing: 0;
            margin-bottom: clamp(12px, 1.8vmin, 24px);
            text-transform: uppercase;
        }}
        [data-fit] {{
            overflow: hidden;
            max-width: 100%;
            overflow-wrap: anywhere;
            word-break: normal;
            letter-spacing: 0;
        }}
        .fit-title {{
            height: min(34vh, 320px);
            color: var(--text);
            font-size: clamp(34px, min(7vw, 7vh), 96px);
            line-height: 1.04;
            font-weight: 900;
        }}
        .compact-title {{ height: min(27vh, 230px); }}
        .quote-title {{
            height: min(36vh, 340px);
            text-align: center;
        }}
        .fit-lead {{
            height: min(21vh, 190px);
            margin-top: clamp(16px, 2.2vmin, 34px);
            color: var(--muted);
            font-size: clamp(18px, min(3vw, 3vh), 38px);
            line-height: 1.34;
            font-weight: 540;
        }}
        .quote-lead {{
            margin-left: auto;
            margin-right: auto;
            max-width: min(980px, 86%);
            text-align: center;
        }}
        .visual-card, .card-grid article, .statement-row {{
            background: color-mix(in srgb, var(--surface) 92%, transparent);
            border: 1px solid color-mix(in srgb, var(--accent) 24%, transparent);
            border-radius: 8px;
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.20);
        }}
        .visual-card {{
            position: relative;
            min-width: 0;
            min-height: 0;
            overflow: hidden;
            padding: clamp(22px, 3.2vmin, 46px);
        }}
        .visual-card.wide {{ min-height: 100%; }}
        .orb {{
            position: absolute;
            border-radius: 50%;
            filter: blur(0.2px);
            opacity: 0.82;
        }}
        .orb.one {{
            width: 44%;
            aspect-ratio: 1;
            top: 9%;
            right: 9%;
            background: radial-gradient(circle, color-mix(in srgb, var(--accent) 42%, transparent), transparent 68%);
        }}
        .orb.two {{
            width: 34%;
            aspect-ratio: 1;
            left: 8%;
            bottom: 10%;
            background: radial-gradient(circle, color-mix(in srgb, var(--accent2) 38%, transparent), transparent 68%);
        }}
        .diagram {{
            position: absolute;
            inset: 18%;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: clamp(12px, 2vmin, 28px);
            transform: rotate(-4deg);
        }}
        .diagram span {{
            border: 2px solid color-mix(in srgb, var(--accent) 58%, transparent);
            background: color-mix(in srgb, var(--surface2) 78%, transparent);
            border-radius: 8px;
            box-shadow: inset 0 0 40px color-mix(in srgb, var(--accent) 14%, transparent);
        }}
        .signal-ring {{
            position: absolute;
            inset: 28%;
            border: 3px solid color-mix(in srgb, var(--accent2) 64%, transparent);
            border-radius: 50%;
        }}
        .timeline-visual, .stats-visual, .compare-visual {{
            position: absolute;
            inset: clamp(24px, 4vmin, 54px);
            display: grid;
            gap: clamp(12px, 2vmin, 24px);
            z-index: 1;
        }}
        .timeline-visual {{
            grid-template-rows: repeat(3, minmax(0, 1fr));
        }}
        .timeline-visual::before {{
            content: "";
            position: absolute;
            left: clamp(12px, 2vmin, 24px);
            top: 10%;
            bottom: 10%;
            width: 3px;
            background: linear-gradient(var(--accent), var(--accent2));
            border-radius: 999px;
        }}
        .timeline-visual div {{
            display: grid;
            grid-template-columns: clamp(32px, 5vmin, 56px) minmax(0, 1fr);
            align-items: center;
            gap: clamp(12px, 2vmin, 22px);
        }}
        .timeline-visual span {{
            width: clamp(20px, 3.2vmin, 36px);
            aspect-ratio: 1;
            border-radius: 999px;
            background: var(--accent2);
            box-shadow: 0 0 0 8px color-mix(in srgb, var(--accent2) 16%, transparent);
            z-index: 2;
        }}
        .timeline-visual p, .stats-visual p, .compare-visual p {{
            min-width: 0;
            color: var(--text);
            font-size: clamp(14px, 1.95vmin, 24px);
            line-height: 1.25;
            font-weight: 680;
            overflow: hidden;
        }}
        .stats-visual {{
            grid-template-columns: repeat(3, minmax(0, 1fr));
            align-items: stretch;
        }}
        .stats-visual div {{
            min-width: 0;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding: clamp(16px, 2.4vmin, 30px);
            border-radius: 8px;
            background: color-mix(in srgb, var(--surface2) 62%, transparent);
            border: 1px solid color-mix(in srgb, var(--accent) 24%, transparent);
        }}
        .stats-visual strong, .compare-visual strong {{
            color: var(--accent2);
            font-size: clamp(28px, 5vmin, 64px);
            line-height: 1;
            font-weight: 920;
        }}
        .compare-visual {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
            align-items: stretch;
        }}
        .compare-visual div {{
            min-width: 0;
            padding: clamp(18px, 3vmin, 40px);
            border-radius: 8px;
            background: color-mix(in srgb, var(--surface2) 64%, transparent);
            border-top: 4px solid var(--accent);
        }}
        .quote-mark {{
            position: absolute;
            inset: 0;
            display: grid;
            place-items: center;
            color: color-mix(in srgb, var(--accent) 34%, transparent);
            font-size: min(42vw, 42vh);
            line-height: 0.8;
            font-weight: 900;
        }}
        .focus-chip {{
            position: absolute;
            left: clamp(22px, 3vmin, 44px);
            top: clamp(22px, 3vmin, 44px);
            color: var(--accent2);
            font-size: clamp(16px, 2.3vmin, 28px);
            font-weight: 900;
        }}
        .fit-point {{
            height: clamp(72px, 12.5vh, 148px);
            color: var(--text);
            font-size: clamp(17px, min(2.35vw, 2.35vh), 30px);
            line-height: 1.28;
            font-weight: 650;
        }}
        .featured {{
            position: absolute;
            left: clamp(22px, 3.2vmin, 46px);
            right: clamp(22px, 3.2vmin, 46px);
            bottom: clamp(22px, 3.2vmin, 46px);
            height: clamp(86px, 17vh, 170px);
            color: var(--muted);
        }}
        .point-stack {{
            flex: 1 1 auto;
            min-height: 0;
            display: grid;
            grid-template-rows: repeat(3, minmax(0, 1fr));
            gap: clamp(12px, 1.8vmin, 22px);
            margin-top: clamp(14px, 2.2vmin, 32px);
        }}
        .point-stack .fit-point, .card-grid .fit-point, .statement-row .fit-point {{
            height: 100%;
            border-left: 4px solid var(--accent2);
            padding: clamp(16px, 2.2vmin, 30px);
            background: color-mix(in srgb, var(--surface2) 56%, transparent);
            border-radius: 8px;
        }}
        .card-grid {{
            min-height: 0;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: clamp(14px, 2.2vmin, 28px);
        }}
        .card-grid article {{
            min-width: 0;
            min-height: 0;
            padding: clamp(16px, 2.2vmin, 30px);
        }}
        .statement-row {{
            min-height: 0;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: clamp(14px, 2vmin, 28px);
            padding: clamp(16px, 2.4vmin, 32px);
        }}
        body.portrait {{
            --pad: clamp(34px, 6vmin, 72px);
            --gap: clamp(18px, 3.4vmin, 42px);
        }}
        .portrait .template-focus,
        .portrait .template-split {{
            grid-template-columns: 1fr;
            grid-template-rows: minmax(0, 0.58fr) minmax(260px, 0.42fr);
        }}
        .portrait .template-split {{
            grid-template-rows: minmax(260px, 0.4fr) minmax(0, 0.6fr);
        }}
        .portrait .template-cards {{
            grid-template-rows: minmax(160px, 0.3fr) minmax(0, 0.7fr);
        }}
        .portrait .card-grid {{
            grid-template-columns: 1fr;
            grid-template-rows: repeat(3, minmax(0, 1fr));
        }}
        .portrait .statement-row {{
            grid-template-columns: 1fr;
            grid-template-rows: repeat(2, minmax(0, 1fr));
        }}
        .portrait .fit-title {{ height: min(25vh, 300px); }}
        .portrait .compact-title {{ height: min(18vh, 220px); }}
        .portrait .fit-lead {{ height: min(14vh, 170px); }}
        .portrait .stats-visual, .portrait .compare-visual {{
            grid-template-columns: 1fr;
            grid-template-rows: repeat(3, minmax(0, 1fr));
        }}
        .portrait .compare-visual {{
            grid-template-rows: repeat(2, minmax(0, 1fr));
        }}
        .square .template-focus,
        .square .template-split {{
            grid-template-columns: 1fr;
            grid-template-rows: minmax(210px, 0.34fr) minmax(0, 0.66fr);
        }}
        .square .template-split .compact-title {{
            height: min(18vh, 170px);
        }}
        .square .template-split .point-stack {{
            gap: clamp(10px, 1.5vmin, 18px);
        }}
        .square .template-split .fit-point {{
            line-height: 1.18;
        }}
        .square .card-grid {{
            grid-template-columns: 1fr;
            grid-template-rows: repeat(3, minmax(0, 1fr));
        }}
        .square .stats-visual {{
            grid-template-columns: 1fr;
            grid-template-rows: repeat(3, minmax(0, 1fr));
        }}
        body.compact {{
            --pad: clamp(24px, 4.4vmin, 66px);
            --gap: clamp(12px, 2.4vmin, 34px);
        }}
        body.dense {{
            --pad: clamp(18px, 3.6vmin, 54px);
            --gap: clamp(10px, 1.8vmin, 28px);
        }}
        .dense .fit-lead {{
            height: min(15vh, 136px);
        }}
        .dense .visual-card {{
            padding: clamp(14px, 2vmin, 30px);
        }}
        .dense .fit-point {{
            line-height: 1.18;
        }}
        .minimal .fit-lead {{
            display: none;
        }}
        .minimal .statement-row {{
            display: none;
        }}
        .minimal .template-quote {{
            grid-template-rows: 1fr;
        }}
    </style>
</head>
<body class="{aspect_class} template-{template_kind}">
{content}
<script>{self._fit_runtime_js()}</script>
</body>
</html>"""

    def _scene_composition_path(self, slide_num: int) -> str:
        return os.path.join(self._html_reels_compositions_dir(), f"scene_{slide_num:02d}.html")

    def _write_html_reels_root(self, html_files: List[str], durations: Optional[List[int]] = None) -> str:
        self._ensure_html_reels_project()
        total = 0.0
        scene_markup = []
        timeline_js = []
        crossfade = 0.3
        for idx, html_file in enumerate(html_files):
            slide_num = idx + 1
            duration = 8.0
            if durations and idx < len(durations):
                duration = float(max(1, int(durations[idx])))
            start = total
            scene_duration = duration + (crossfade if idx < len(html_files) - 1 else 0)
            total += duration
            rel = Path(html_file).resolve().relative_to(Path(self.HTML_REELS_DIR).resolve()).as_posix()
            track = 10 + (idx % 2)
            scene_markup.append(
                f"""      <div id="scene-{slide_num:02d}" class="clip scene-slot"
        data-composition-id="scene-{slide_num:02d}" data-composition-src="{rel}"
        data-start="{start:.3f}" data-duration="{scene_duration:.3f}" data-track-index="{track}"
        data-width="{self.width}" data-height="{self.height}"></div>"""
            )
            if idx < len(html_files) - 1:
                timeline_js.append(
                    f"""      tl.to("#scene-{slide_num:02d}", {{ opacity: 0, duration: {crossfade}, ease: "power2.inOut" }}, {max(0, total - crossfade):.3f});
      tl.set("#scene-{slide_num:02d}", {{ opacity: 0 }}, {total:.3f});"""
                )

        index_path = os.path.join(self.HTML_REELS_DIR, "index.html")
        html_lang = "vi" if self.output_language == "vi" else "en"
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(f"""<!doctype html>
<html lang="{html_lang}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={self.width}, height={self.height}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{
        width: {self.width}px;
        height: {self.height}px;
        overflow: hidden;
        background: #05070d;
        font-family: "Segoe UI", Arial, "Noto Sans", sans-serif;
      }}
      #root {{
        position: absolute;
        inset: 0;
        overflow: hidden;
        background:
          radial-gradient(circle at 18% 16%, rgba(56,189,248,0.10), transparent 28%),
          radial-gradient(circle at 82% 74%, rgba(244,63,94,0.10), transparent 30%),
          #05070d;
      }}
      .scene-slot {{
        position: absolute;
        inset: 0;
        width: {self.width}px;
        height: {self.height}px;
        overflow: hidden;
      }}
    </style>
  </head>
  <body>
    <main id="root" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="{self.width}" data-height="{self.height}">
{os.linesep.join(scene_markup)}
    </main>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
{os.linesep.join(timeline_js)}
      window.__timelines.main = tl;
    </script>
  </body>
</html>""")
        return index_path

    def generate_html_slides(self, plan: VideoPlan, resume: bool = False, max_workers: int = 1) -> List[str]:
        """
        Ask the model to code each HTML scene into a HyperFrames project.
        """
        self._ensure_html_reels_project()
        html_files = []
        html_cache_current = self._is_html_cache_current(len(plan.slides))
        if resume and not html_cache_current:
            self._log("   ℹ️ Cache HTML cũ không khớp size đã chọn, sẽ tạo lại HTML.")

        if max(1, int(max_workers or 1)) > 1:
            return self._generate_html_slides_parallel(plan, resume, html_cache_current, max_workers)

        for slide in plan.slides:
            html_path = self._scene_composition_path(slide.slide_number)
            if resume and html_cache_current and self._is_valid_file(html_path, min_size=50):
                html_files.append(html_path)
                self._log(f"   🔁 Dùng lại HTML cảnh {slide.slide_number}: {html_path}")
                continue

            self._log(f"💻 AI đang code HyperFrames scene {slide.slide_number}/{plan.total_slides}...")

            html_content = self._generate_single_html(slide)

            # Lưu file HTML
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            html_files.append(html_path)
            self._log(f"   ✅ Đã lưu: {html_path}")

        if len(html_files) == len(plan.slides):
            self._write_html_cache(len(plan.slides))
        return html_files

    def _generate_html_slides_parallel(
        self,
        plan: VideoPlan,
        resume: bool,
        html_cache_current: bool,
        max_workers: int,
    ) -> List[str]:
        html_files = [None] * len(plan.slides)
        pending = []
        for idx, slide in enumerate(plan.slides):
            html_path = self._scene_composition_path(slide.slide_number)
            if resume and html_cache_current and self._is_valid_file(html_path, min_size=50):
                html_files[idx] = html_path
                self._log(f"   🔁 Dùng lại HTML cảnh {slide.slide_number}: {html_path}")
                continue
            pending.append((idx, slide, html_path))

        def generate_one(item):
            idx, slide, html_path = item
            self._log(f"💻 AI đang code HyperFrames scene {slide.slide_number}/{plan.total_slides}...")
            html_content = self._generate_single_html(slide)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return idx, html_path

        workers = max(1, int(max_workers or 1))
        if pending:
            self._log(f"⚡ AI code HyperFrames scenes song song với {workers} workers...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(generate_one, item) for item in pending]
            for future in as_completed(futures):
                idx, html_path = future.result()
                html_files[idx] = html_path
                self._log(f"   ✅ Đã lưu: {html_path}")

        html_files = [path for path in html_files if path]
        if len(html_files) == len(plan.slides):
            self._write_html_cache(len(plan.slides))
        return html_files

    def _generate_single_html(self, slide: SlideContent) -> str:
        """Ask the model to code the whole slide, then add compositor safety."""
        return self._generate_single_html_with_ai(slide)

    def _generate_single_html_with_ai(self, slide: SlideContent) -> str:
        """Ask the model to code the full visual scene for one slide."""
        preset = self._preset()
        language_rules = self._language_rules()
        html_lang = "vi" if self.output_language == "vi" else "en"
        style_label = self._ui_text(preset["label"], preset.get("label_en", preset["label"]))

        prompt = f"""Hãy tự code một file HTML/CSS composition hoàn chỉnh cho MỘT CẢNH VIDEO chuyên nghiệp theo phong cách HyperFrames.

THÔNG TIN NỘI DUNG:
- Tiêu đề cảnh: {slide.title}
- Ý tưởng để chuyển thành hình ảnh/visual: {slide.html_idea}
- Template gợi ý: {getattr(slide, "template_id", "") or "AI tự chọn"}
- Visual type gợi ý: {getattr(slide, "visual_type", "") or "AI tự chọn"}
- Sắc thái: {getattr(slide, "emphasis", "") or "cinematic"}
- Phong cách: {style_label}
- Kích thước bắt buộc: width={self.width}px, height={self.height}px
- Ngôn ngữ HTML: {html_lang}

MÀU THAM CHIẾU:
- Nền: {preset["bg"]}
- Bề mặt: {preset["surface"]}
- Chữ: {preset["text"]}
- Chữ phụ: {preset["muted"]}
- Nhấn 1: {preset["accent"]}
- Nhấn 2: {preset["accent2"]}

QUY TẮC NGÔN NGỮ:
{language_rules}

YÊU CẦU CỰC KỲ QUAN TRỌNG:
1. Code một composition HTML/CSS/JS giống repo video-reels-agent: root có `data-composition-id="slide-{slide.slide_number}"`, `data-width="{self.width}"`, `data-height="{self.height}"`, `data-duration="{max(1, int(getattr(slide, "duration_seconds", 8) or 8))}"`.
2. Các phần tử xuất hiện theo thời gian dùng class `clip` và metadata `data-start`, `data-duration`, `data-track-index`. Dùng track rõ ràng, ví dụ visual=1, label=2, title=3, detail=4. Trên cùng một track, tuyệt đối không để clip overlap: `data-start` của clip sau phải >= `data-start + data-duration` của clip trước, hoặc chuyển sang track khác.
3. Được dùng GSAP qua CDN `https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js` và phải đăng ký timeline paused: `window.__timelines = window.__timelines || {{}}; window.__timelines["slide-{slide.slide_number}"] = tl;`.
4. Tạo motion thật sự: entrance, subtle pulse, sweep, counter giả lập, chart reveal, connector draw, crossfade nhỏ. Không dùng `repeat: -1`; nếu lặp thì dùng số hữu hạn theo duration.
5. BẮT BUỘC mọi nội dung nằm trong canvas {self.width}x{self.height}px. Tuyệt đối KHÔNG dùng scroll dưới bất kỳ dạng nào. Nếu nội dung dài, giảm chữ, giảm font, chia ít khối hơn hoặc ưu tiên visual.
6. Đánh dấu các khối quan trọng bằng `data-block`, ví dụ `data-block="title"`, `data-block="visual"`, `data-block="metric"`, `data-block="label"`.
7. KHÔNG chép nguyên văn phần "Ý tưởng" / prompt / mô tả thiết kế vào video. Chỉ hiển thị chữ thật sự cần cho người xem.
8. Không hiển thị số cảnh, số slide, "Slide 01", "Cảnh 1", thời lượng, progress dots, hoặc dấu hiệu debug/template.
9. Không dùng external image, Google Fonts, audio, video. Chỉ HTML/CSS/SVG inline và GSAP CDN. Text dùng Segoe UI / Arial / Noto Sans, letter-spacing 0, không tràn/đè nhau.
10. Mỗi phần tử timeline-visible cần có `id` ổn định, dễ đọc, ví dụ `id="scene-{slide.slide_number}-title"` hoặc `id="scene-{slide.slide_number}-metric-1"`.
11. Giữ file gọn để HyperFrames strict lint chạy được: tối đa 260 dòng, tối đa 4 phần tử có data-start trên mỗi `data-track-index`; nếu cần nhiều chi tiết, gộp visual/text thành ít block hơn.
12. Trả về DUY NHẤT code HTML, không giải thích, không markdown.
"""

        try:
            response = self.text_provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Bạn là một motion/art director và senior HyperFrames HTML/CSS designer. "
                            "Bạn chỉ trả về HTML composition sạch, có clip metadata và timeline paused render được ngay trong Chromium."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.55, "num_predict": 8192},
            )

            raw = response["message"]["content"]
            html = self._extract_html(raw)
            if html:
                return self._apply_render_safety(html)

        except Exception as e:
            self._log(f"   ⚠️ Lỗi sinh HTML từ AI, dùng fallback tối giản: {e}")

        return self._fallback_html(slide)

    def _apply_render_safety(self, html: str) -> str:
        """Inject a compositor guard around AI-authored HTML slides."""
        safe_css = f"""
    <style id="aivc-render-safety">
        *, *::before, *::after {{
            box-sizing: border-box !important;
        }}
        html, body, body *, .title, .subtitle {{
            font-family: "Segoe UI", Arial, Tahoma, "Noto Sans", sans-serif !important;
            letter-spacing: 0 !important;
            text-rendering: geometricPrecision;
            -webkit-font-smoothing: antialiased;
            overflow-wrap: anywhere;
            word-break: normal;
            hyphens: auto;
        }}
        html, body {{
            width: {self.width}px !important;
            height: {self.height}px !important;
            margin: 0 !important;
            overflow: hidden !important;
            background: #05070d;
        }}
        body {{
            position: relative !important;
            padding: 0 !important;
        }}
        #aivc-stage {{
            position: fixed !important;
            inset: 0 !important;
            width: {self.width}px !important;
            height: {self.height}px !important;
            overflow: hidden !important;
            contain: layout paint style !important;
            transform-origin: 0 0 !important;
            background: inherit;
        }}
        #aivc-fit-root {{
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            width: {self.width}px !important;
            height: {self.height}px !important;
            overflow: visible !important;
            transform-origin: 0 0 !important;
        }}
        #aivc-stage *,
        #aivc-stage *::before,
        #aivc-stage *::after {{
            scrollbar-width: none !important;
        }}
        #aivc-stage *::-webkit-scrollbar {{
            display: none !important;
        }}
        #aivc-stage [style*="overflow: auto"],
        #aivc-stage [style*="overflow:auto"],
        #aivc-stage [style*="overflow-y: auto"],
        #aivc-stage [style*="overflow-y:auto"],
        #aivc-stage [style*="overflow: scroll"],
        #aivc-stage [style*="overflow:scroll"],
        #aivc-stage [style*="overflow-y: scroll"],
        #aivc-stage [style*="overflow-y:scroll"] {{
            overflow: hidden !important;
        }}
        img, video, svg, canvas {{
            max-width: 100% !important;
            max-height: 100% !important;
        }}
        .aivc-fit-text {{
            overflow: hidden !important;
            overflow-wrap: anywhere !important;
            word-break: normal !important;
            hyphens: auto !important;
        }}
        body.aivc-compact .aivc-fit-text {{
            line-height: 1.15 !important;
        }}
    </style>
"""
        safe_js = f"""
    <script id="aivc-compositor-guard">
    (() => {{
        const WIDTH = {self.width};
        const HEIGHT = {self.height};
        const EPS = 4;
        const px = (value, fallback) => {{
            const parsed = Number.parseFloat(value);
            return Number.isFinite(parsed) ? parsed : fallback;
        }};
        const overflows = (el) => el.scrollWidth > el.clientWidth + EPS || el.scrollHeight > el.clientHeight + EPS;
        const disableScrollContainers = (root) => {{
            root.querySelectorAll("*").forEach((el) => {{
                const style = getComputedStyle(el);
                if (["auto", "scroll"].includes(style.overflow) || ["auto", "scroll"].includes(style.overflowY) || ["auto", "scroll"].includes(style.overflowX)) {{
                    el.dataset.aivcScrollDisabled = "1";
                    el.style.overflow = "hidden";
                    el.style.overflowX = "hidden";
                    el.style.overflowY = "hidden";
                }}
            }});
        }};
        const interestingText = (el) => {{
            if (!el || el.children.length > 0) return false;
            const text = (el.textContent || "").trim();
            if (text.length < 18) return false;
            const style = getComputedStyle(el);
            return style.display !== "none" && style.visibility !== "hidden";
        }};
        const fitText = (el) => {{
            const style = getComputedStyle(el);
            const original = el.dataset.aivcOriginalText || el.textContent || "";
            el.dataset.aivcOriginalText = original;
            el.textContent = original;
            el.classList.add("aivc-fit-text");
            const current = px(style.fontSize, 28);
            const min = Math.max(11, Math.min(22, current * 0.48));
            let low = min;
            let high = current;
            for (let i = 0; i < 18; i += 1) {{
                const mid = (low + high) / 2;
                el.style.fontSize = `${{mid}}px`;
                if (overflows(el)) high = mid;
                else low = mid;
            }}
            el.style.fontSize = `${{Math.floor(low * 10) / 10}}px`;
            if (!overflows(el)) return;
            const words = original.split(/\\s+/).filter(Boolean);
            let left = 1;
            let right = words.length;
            while (left < right) {{
                const mid = Math.ceil((left + right) / 2);
                el.textContent = `${{words.slice(0, mid).join(" ").replace(/[\\s.,!?:;]+$/, "")}}...`;
                if (overflows(el)) right = mid - 1;
                else left = mid;
            }}
            el.textContent = `${{words.slice(0, Math.max(1, left)).join(" ").replace(/[\\s.,!?:;]+$/, "")}}...`;
        }};
        const ensureStage = () => {{
            let stage = document.getElementById("aivc-stage");
            if (!stage) {{
                stage = document.createElement("main");
                stage.id = "aivc-stage";
                stage.dataset.compositionId = "ai-slide";
                stage.dataset.width = String(WIDTH);
                stage.dataset.height = String(HEIGHT);
                stage.dataset.duration = "full";
                const root = document.createElement("div");
                root.id = "aivc-fit-root";
                const nodes = Array.from(document.body.childNodes).filter((node) => {{
                    if (node.nodeType === Node.TEXT_NODE) return node.textContent.trim();
                    if (node.nodeType !== Node.ELEMENT_NODE) return false;
                    return !["SCRIPT", "STYLE", "LINK", "META"].includes(node.tagName) && node.id !== "aivc-stage";
                }});
                for (const node of nodes) root.appendChild(node);
                stage.appendChild(root);
                document.body.appendChild(stage);
            }}
            stage.dataset.width = String(WIDTH);
            stage.dataset.height = String(HEIGHT);
            stage.style.width = `${{WIDTH}}px`;
            stage.style.height = `${{HEIGHT}}px`;
            let root = document.getElementById("aivc-fit-root");
            if (!root) {{
                root = document.createElement("div");
                root.id = "aivc-fit-root";
                while (stage.firstChild) root.appendChild(stage.firstChild);
                stage.appendChild(root);
            }}
            disableScrollContainers(root);
            return {{stage, root}};
        }};
        const contentBox = (root) => {{
            const elements = Array.from(root.querySelectorAll("*")).filter((el) => {{
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 1 && rect.height > 1 && style.display !== "none" && style.visibility !== "hidden";
            }});
            if (!elements.length) return root.getBoundingClientRect();
            let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
            for (const el of elements) {{
                const rect = el.getBoundingClientRect();
                left = Math.min(left, rect.left);
                top = Math.min(top, rect.top);
                right = Math.max(right, rect.right);
                bottom = Math.max(bottom, rect.bottom);
            }}
            return {{left, top, right, bottom, width: right - left, height: bottom - top}};
        }};
        const fitComposition = () => {{
            const {{root}} = ensureStage();
            disableScrollContainers(root);
            root.style.transform = "translate(0px, 0px) scale(1)";
            root.querySelectorAll("h1,h2,h3,p,li,span,strong,em,div[data-block],.title,.subtitle,.label").forEach((el) => {{
                if (interestingText(el)) fitText(el);
            }});
            const box = contentBox(root);
            if (!box.width || !box.height) return true;
            const margin = Math.max(12, Math.round(Math.min(WIDTH, HEIGHT) * 0.025));
            const availableW = WIDTH - margin * 2;
            const availableH = HEIGHT - margin * 2;
            const scale = Math.min(1, availableW / Math.max(1, box.width), availableH / Math.max(1, box.height));
            const tx = margin - box.left * scale + Math.max(0, (availableW - box.width * scale) / 2);
            const ty = margin - box.top * scale + Math.max(0, (availableH - box.height * scale) / 2);
            root.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
            root.dataset.aivcScale = String(scale);
            return true;
        }};
        const qa = () => {{
            const {{root}} = ensureStage();
            const bad = [];
            if (document.documentElement.scrollWidth > WIDTH + EPS || document.documentElement.scrollHeight > HEIGHT + EPS) {{
                bad.push({{type: "page-scroll", w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight}});
            }}
            const box = contentBox(root);
            if (box.left < -EPS || box.top < -EPS || box.right > WIDTH + EPS || box.bottom > HEIGHT + EPS) {{
                bad.push({{type: "composition-bounds", left: box.left, top: box.top, right: box.right, bottom: box.bottom}});
            }}
            root.querySelectorAll(".aivc-fit-text").forEach((el) => {{
                if (overflows(el)) {{
                    const name = el.tagName.toLowerCase() + (el.className ? "." + String(el.className).split(/\\s+/).slice(0, 2).join(".") : "");
                    bad.push({{type: "text-overflow", name, sw: el.scrollWidth, sh: el.scrollHeight, cw: el.clientWidth, ch: el.clientHeight}});
                }}
            }});
            root.querySelectorAll("[data-aivc-scroll-disabled='1']").forEach((el) => {{
                if (el.scrollHeight > el.clientHeight + EPS || el.scrollWidth > el.clientWidth + EPS) {{
                    const name = el.tagName.toLowerCase() + (el.className ? "." + String(el.className).split(/\\s+/).slice(0, 2).join(".") : "");
                    bad.push({{type: "disabled-scroll-overflow", name, sw: el.scrollWidth, sh: el.scrollHeight, cw: el.clientWidth, ch: el.clientHeight}});
                }}
            }});
            return {{ok: bad.length === 0, bad: bad.slice(0, 8), scale: Number(root.dataset.aivcScale || "1")}};
        }};
        const seek = (seconds = 0) => {{
            ensureStage();
            if (window.__timelines) {{
                Object.values(window.__timelines).forEach((tl) => {{
                    if (!tl) return;
                    try {{
                        if (typeof tl.pause === "function") tl.pause();
                        if (typeof tl.time === "function") tl.time(seconds, false);
                        else if (typeof tl.seek === "function") tl.seek(seconds, false);
                    }} catch (error) {{}}
                }});
            }}
            document.querySelectorAll("#aivc-stage .clip, #aivc-stage [data-start]").forEach((el) => {{
                const start = Number.parseFloat(el.dataset.start || "0") || 0;
                const rawDuration = el.dataset.duration || "999999";
                const duration = rawDuration === "full" ? 999999 : (Number.parseFloat(rawDuration) || 999999);
                const visible = seconds >= start && seconds <= start + duration;
                el.style.visibility = visible ? "visible" : "hidden";
                el.style.pointerEvents = visible ? "" : "none";
            }});
            return true;
        }};
        window.__aivcPrepareComposition = ensureStage;
        window.__aivcFitSlide = fitComposition;
        window.__aivcQaSlide = qa;
        window.__aivcSeek = seek;
        window.__aivcRepairSlide = (level = "compact") => {{
            document.body.classList.add(`aivc-${{level}}`);
            fitComposition();
            return qa();
        }};
        if (document.readyState === "loading") {{
            document.addEventListener("DOMContentLoaded", fitComposition, {{once: true}});
        }} else {{
            fitComposition();
        }}
    }})();
    </script>
"""
        if "<meta charset" not in html.lower():
            html = re.sub(r"<head([^>]*)>", r'<head\1>\n    <meta charset="UTF-8">', html, count=1, flags=re.IGNORECASE)
        if "</head>" in html.lower():
            html = re.sub(r"</head>", lambda _: safe_css + "</head>", html, count=1, flags=re.IGNORECASE)
        else:
            html = safe_css + html
        if "</body>" in html.lower():
            return re.sub(r"</body>", lambda _: safe_js + "</body>", html, count=1, flags=re.IGNORECASE)
        return html + safe_js

    def _extract_html(self, text: str) -> Optional[str]:
        """Trích xuất code HTML từ phản hồi LLM."""
        # Tìm trong code block
        match = re.search(r'```html\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        match = re.search(r'```\s*(<!DOCTYPE.*?</html>)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Tìm trực tiếp
        match = re.search(r'(<!DOCTYPE.*?</html>)', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Nếu bắt đầu bằng <
        if text.strip().startswith('<'):
            return text.strip()

        return None

    def _fallback_html(self, slide: SlideContent) -> str:
        """HTML mặc định nếu LLM thất bại."""
        anim_css = ""
        preset = self._preset()
        html_lang = "vi" if self.output_language == "vi" else "en"

        return f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{ width: {self.width}px; height: {self.height}px; overflow: hidden; }}
        body {{
            padding: clamp(34px, 5vmin, 88px);
            background:
                radial-gradient(circle at 18% 22%, {preset["accent"]}33, transparent 28%),
                radial-gradient(circle at 82% 74%, {preset["accent2"]}30, transparent 30%),
                linear-gradient(135deg, {preset["bg"]}, {preset["surface2"]});
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: "Segoe UI", Arial, Tahoma, "Noto Sans", sans-serif;
            color: {preset["text"]};
            text-rendering: geometricPrecision;
            -webkit-font-smoothing: antialiased;
        }}
        .frame {{
            width: 100%;
            height: 100%;
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(260px, 0.72fr);
            gap: clamp(24px, 5vmin, 72px);
            align-items: center;
        }}
        h1 {{
            font-size: clamp(38px, min(7vw, 7vh), 96px);
            line-height: 1.05;
            font-weight: 900;
            letter-spacing: 0;
            max-width: 980px;
            background: linear-gradient(90deg, {preset["accent"]}, {preset["accent2"]});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .visual {{
            position: relative;
            width: min(100%, 520px);
            aspect-ratio: 1;
            border-radius: 8px;
            background: {preset["surface"]};
            border: 1px solid {preset["accent"]}55;
            box-shadow: 0 28px 90px rgba(0,0,0,0.22);
            overflow: hidden;
        }}
        .visual::before, .visual::after {{
            content: "";
            position: absolute;
            inset: 14%;
            border: 2px solid {preset["accent"]};
            transform: rotate(12deg);
        }}
        .visual::after {{
            inset: 28%;
            border-color: {preset["accent2"]};
            transform: rotate(-18deg);
            background: {preset["accent2"]}22;
        }}
        {anim_css}
    </style>
</head>
<body>
    <main class="frame">
        <h1>{html_lib.escape(slide.title)}</h1>
        <section class="visual" aria-hidden="true"></section>
    </main>
</body>
</html>"""

    # ──────────────────────────────────────
    # Giai đoạn 3: Render HTML → Video
    # ──────────────────────────────────────
    def _render_with_hyperframes(self, html_files: List[str], durations: Optional[List[int]], resume: bool = False) -> Optional[str]:
        self._ensure_html_reels_project()
        index_path = self._write_html_reels_root(html_files, durations)
        output_path = self._html_reels_render_path()
        if resume and self._is_render_cache_current(html_files) and self._is_valid_file(output_path, min_size=1024):
            self._log(f"   🔁 Dùng lại video HyperFrames: {output_path}")
            return output_path

        node_path = shutil.which("node")
        npx_path = shutil.which("npx")
        if not node_path or not npx_path:
            self._log("   ⚠️ Không tìm thấy Node.js/npx, fallback sang Playwright renderer.")
            return None

        quality = "draft" if self.width * self.height < 1280 * 720 else "standard"
        fps = 30
        project_dir = os.path.abspath(self.HTML_REELS_DIR)
        render_output = os.path.abspath(output_path)
        base_cmd = [
            npx_path,
            "--yes",
            "hyperframes@0.6.12",
            "render",
            project_dir,
            "--output",
            render_output,
            "--fps",
            str(fps),
            "--quality",
            quality,
        ]
        cmd = base_cmd + ["--strict"]
        self._log(f"🎬 Render HyperFrames project: {index_path}")
        try:
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60 * 30,
            )
        except Exception as e:
            self._log(f"   ⚠️ Không chạy được HyperFrames ({e}), fallback sang Playwright renderer.")
            return None

        if result.returncode != 0:
            render_log = (result.stderr or result.stdout or "").strip()
            tail = render_log.splitlines()[-8:]
            if tail:
                self._log("   ⚠️ HyperFrames render lỗi:\n" + "\n".join(tail))
            self._log("   ↪️ Fallback sang Playwright renderer.")
            return None
        if not self._is_valid_file(output_path, min_size=1024):
            self._log("   ⚠️ HyperFrames không tạo file MP4 hợp lệ, fallback sang Playwright renderer.")
            return None
        self._log(f"   ✅ HyperFrames MP4: {output_path}")
        return output_path

    def render_slides_to_video(self, html_files: List[str], durations: Optional[List[int]] = None, resume: bool = False) -> List[str]:
        hyperframes_video = self._render_with_hyperframes(html_files, durations, resume=resume)
        if hyperframes_video:
            self._write_render_cache(len(html_files))
            return [hyperframes_video]
        return self._render_slides_to_video_playwright(html_files, durations=durations, resume=resume)

    def _render_slides_to_video_playwright(self, html_files: List[str], durations: Optional[List[int]] = None, resume: bool = False) -> List[str]:
        """
        Dùng Playwright headless để render HTML/CSS composition theo timeline,
        chụp frame sequence rồi encode thành MP4.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: python -m pip install playwright && python -m playwright install chromium"
            ) from exc

        video_clips = []

        if resume and self._is_render_cache_current(html_files):
            cached_clips = []
            for idx, _ in enumerate(html_files):
                cached_path = os.path.join(self.TEMP_DIR, f"slide_{idx + 1}.mp4")
                if self._is_valid_file(cached_path, min_size=1024):
                    cached_clips.append(cached_path)
                else:
                    cached_clips = []
                    break
            if cached_clips:
                for path in cached_clips:
                    self._log(f"   🔁 Dùng lại video HTML/CSS đã render: {path}")
                self._log(f"✅ Đã dùng lại {len(cached_clips)} video clips")
                return cached_clips
        elif resume:
            self._log("   ℹ️ Cache video cũ không khớp phiên bản render HTML/CSS mới, sẽ render lại.")

        fps = max(6, int(self.HTML_VIDEO_FPS or 12))
        self._log(f"🎥 Khởi động Playwright để render HTML/CSS timeline ({fps} fps)...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for idx, html_file in enumerate(html_files):
                    slide_num = idx + 1
                    duration = 8
                    if durations and idx < len(durations):
                        duration = max(1, int(durations[idx]))

                    final_video_path = os.path.join(self.TEMP_DIR, f"slide_{slide_num}.mp4")
                    frame_dir = os.path.join(self.TEMP_DIR, f"frame_tmp_{slide_num}")
                    frame_paths = []

                    if resume and self._is_valid_file(final_video_path, min_size=1024):
                        video_clips.append(final_video_path)
                        self._log(f"   🔁 Dùng lại video cảnh {slide_num}: {final_video_path}")
                        continue

                    frame_count = max(1, int(round(duration * fps)))
                    self._log(f"   🎞️ Render cảnh HTML/CSS {slide_num}/{len(html_files)}: {frame_count} frames...")
                    shutil.rmtree(frame_dir, ignore_errors=True)
                    os.makedirs(frame_dir, exist_ok=True)

                    context = browser.new_context(
                        viewport={"width": self.width, "height": self.height},
                        device_scale_factor=self.ANIMATED_FRAME_SCALE,
                    )
                    try:
                        page = context.new_page()
                        file_url = Path(html_file).resolve().as_uri()
                        page.goto(file_url, wait_until="networkidle")
                        page.add_style_tag(content=self._static_render_css())
                        self._prepare_slide_page(page, slide_num)
                        for frame_index in range(frame_count):
                            seconds = min(duration, frame_index / fps)
                            frame_path = os.path.join(frame_dir, f"frame_{frame_index:05d}.png")
                            self._seek_slide_page(page, seconds)
                            page.screenshot(
                                path=frame_path,
                                full_page=False,
                                scale="device",
                            )
                            frame_paths.append(frame_path)
                    finally:
                        context.close()

                    if self._write_frame_sequence_video(frame_paths, final_video_path, fps):
                        video_clips.append(final_video_path)
                        self._log(f"   ✅ Đã render video HTML/CSS: {final_video_path}")

                    shutil.rmtree(frame_dir, ignore_errors=True)
            finally:
                browser.close()

        self._log(f"✅ Đã render xong {len(video_clips)} đoạn video HTML/CSS")
        if len(video_clips) == len(html_files):
            self._write_render_cache(len(html_files))
        return video_clips

    def render_preview_images(self, html_files: List[str], resume: bool = False) -> List[str]:
        """Xuất PNG preview cho từng cảnh trước khi render video."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: python -m pip install playwright && python -m playwright install chromium"
            ) from exc

        os.makedirs(self.PREVIEW_DIR, exist_ok=True)
        preview_paths = []
        self._log("🖼️ Xuất preview PNG cho các cảnh...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for idx, html_file in enumerate(html_files):
                    slide_num = idx + 1
                    preview_path = os.path.join(self.PREVIEW_DIR, f"slide_{slide_num}.png")
                    if (
                        resume
                        and self._is_valid_file(preview_path, min_size=1024)
                        and os.path.getmtime(preview_path) >= os.path.getmtime(html_file)
                    ):
                        preview_paths.append(preview_path)
                        self._log(f"   🔁 Dùng lại preview: {preview_path}")
                        continue

                    context = browser.new_context(
                        viewport={"width": self.width, "height": self.height},
                        device_scale_factor=1,
                    )
                    try:
                        page = context.new_page()
                        page.goto(Path(html_file).resolve().as_uri(), wait_until="networkidle")
                        page.add_style_tag(content=self._static_render_css())
                        self._prepare_slide_page(page, slide_num)
                        self._seek_slide_page(page, 0.6)
                        page.screenshot(
                            path=preview_path,
                            full_page=False,
                            scale="css",
                        )
                        preview_paths.append(preview_path)
                        self._log(f"   ✅ Preview cảnh {slide_num}: {preview_path}")
                    finally:
                        context.close()
            finally:
                browser.close()

        self._log(f"✅ Đã xuất {len(preview_paths)} preview PNG trong {self.PREVIEW_DIR}")
        return preview_paths

    def cleanup(self):
        """Dọn dẹp thư mục tạm."""
        if os.path.exists(self.TEMP_DIR):
            shutil.rmtree(self.TEMP_DIR, ignore_errors=True)
            self._log("🧹 Đã dọn dẹp thư mục tạm")
