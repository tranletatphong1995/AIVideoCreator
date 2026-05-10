"""
Module 1: Video Agent
- Brainstorm ý tưởng qua Ollama → JSON cấu trúc (Pydantic)
- Generate HTML/CSS cho từng slide (có animation)
- Render HTML → video clip bằng Playwright headless browser
"""

import os
import json
import re
import sys
import html as html_lib
import time
import shutil
from typing import List, Optional
from pathlib import Path

from pydantic import BaseModel, Field
import ollama


# ══════════════════════════════════════
# Pydantic Models - Cấu trúc dữ liệu
# ══════════════════════════════════════

class SlideContent(BaseModel):
    """Nội dung 1 slide."""
    slide_number: int = Field(description="Số thứ tự slide")
    title: str = Field(description="Tiêu đề slide")
    html_idea: str = Field(description="Mô tả ý tưởng thiết kế HTML/CSS cho slide")
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
    HTML_CACHE_VERSION = 3
    RENDER_CACHE_VERSION = 5
    STATIC_FRAME_SCALE = 2
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
    ):
        """
        Args:
            model_name: Tên mô hình Ollama (ví dụ: qwen2.5-coder)
            signals: WorkerSignals từ UI để gửi log
            resolution: Tuple (width, height) cho kích thước video
        """
        self.model_name = model_name
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

    def _is_html_cache_current(self, slide_count: int) -> bool:
        try:
            with open(self._html_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                data.get("version") == self.HTML_CACHE_VERSION
                and data.get("resolution") == [self.width, self.height]
                and data.get("style_preset") == self.style_preset
                and data.get("output_language") == self.output_language
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
            body {{
                padding: clamp(28px, 5vmin, 96px) !important;
            }}
            body > * {{
                max-width: 100% !important;
            }}
            h1, .title {{
                max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
                font-size: clamp(32px, min(7vw, 7vh), 92px) !important;
                line-height: 1.08 !important;
            }}
            h2, h3 {{
                max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
                font-size: clamp(24px, min(5vw, 5vh), 64px) !important;
                line-height: 1.15 !important;
            }}
            p, .subtitle, li {{
                max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
                font-size: clamp(18px, min(3.4vw, 3.4vh), 38px) !important;
                line-height: 1.45 !important;
            }}
            img, video, svg, canvas {{
                max-width: 100% !important;
                max-height: 100% !important;
            }}
        """

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

    def _is_render_cache_current(self, html_files: List[str]) -> bool:
        try:
            with open(self._render_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                data.get("version") == self.RENDER_CACHE_VERSION
                and data.get("resolution") == [self.width, self.height]
                and data.get("style_preset") == self.style_preset
                and data.get("output_language") == self.output_language
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
            "html_idea": "Mô tả chi tiết thiết kế HTML/CSS: bố cục, màu sắc, icon, hiệu ứng",
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
- animation_style ưu tiên "none"; các slide là frame tĩnh sắc nét, không chuyển động
- Mỗi slide nên có duration_seconds từ 6-12 giây
- html_idea phải mô tả đủ chi tiết để viết HTML/CSS hoàn chỉnh
- image_prompt dùng riêng cho Fooocus tạo ảnh minh họa theo chủ đề/cảnh; viết bằng tiếng Anh mô tả cảnh, ánh sáng, nhân vật/vật thể, mood, bố cục
- image_prompt tuyệt đối KHÔNG yêu cầu chữ trong ảnh: no text, no captions, no subtitle, no watermark, no logo
"""

        try:
            response = ollama.chat(
                model=self.model_name,
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

    def _slide_points(self, text: str, max_points: int = 3) -> List[str]:
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

    def _template_html(self, slide: SlideContent) -> str:
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

    def generate_html_slides(self, plan: VideoPlan, resume: bool = False) -> List[str]:
        """
        Với mỗi slide, gọi Ollama viết HTML/CSS đầy đủ.
        Trả về danh sách đường dẫn file HTML.
        """
        html_files = []
        html_cache_current = self._is_html_cache_current(len(plan.slides))
        if resume and not html_cache_current:
            self._log("   ℹ️ Cache HTML cũ không khớp size đã chọn, sẽ tạo lại HTML.")

        for slide in plan.slides:
            html_path = os.path.join(self.TEMP_DIR, f"slide_{slide.slide_number}.html")
            if resume and html_cache_current and self._is_valid_file(html_path, min_size=50):
                html_files.append(html_path)
                self._log(f"   🔁 Dùng lại HTML cảnh {slide.slide_number}: {html_path}")
                continue

            self._log(f"💻 Đang viết HTML cho cảnh {slide.slide_number}/{plan.total_slides}...")

            html_content = self._generate_single_html(slide)

            # Lưu file HTML
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            html_files.append(html_path)
            self._log(f"   ✅ Đã lưu: {html_path}")

        if len(html_files) == len(plan.slides):
            self._write_html_cache(len(plan.slides))
        return html_files

    def _generate_single_html(self, slide: SlideContent) -> str:
        """Ask the model to code the full visual scene for one slide."""
        preset = self._preset()
        language_rules = self._language_rules()
        html_lang = "vi" if self.output_language == "vi" else "en"
        style_label = self._ui_text(preset["label"], preset.get("label_en", preset["label"]))

        prompt = f"""Hãy tự code một file HTML/CSS hoàn chỉnh cho MỘT CẢNH VIDEO chuyên nghiệp.

THÔNG TIN NỘI DUNG:
- Tiêu đề cảnh: {slide.title}
- Ý tưởng để chuyển thành hình ảnh/visual: {slide.html_idea}
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
1. KHÔNG chép nguyên văn phần "Ý tưởng" / prompt / mô tả thiết kế vào video.
2. Chỉ hiển thị chữ thật sự cần cho người xem: tiêu đề ngắn, vài nhãn ngắn nếu cần. Ưu tiên visual hơn chữ.
3. KHÔNG hiển thị số cảnh, số slide, "Slide 01", "Cảnh 1", thời lượng, progress dots, hoặc bất kỳ dấu hiệu template/debug nào.
4. Tạo visual bằng HTML/CSS/SVG inline: minh họa, biểu đồ giả lập, timeline, bản đồ khái niệm, icon line-art, dashboard, hoặc scene trừu tượng phù hợp nội dung.
5. Thiết kế phải giống frame video đã hoàn thiện, không giống trang web demo, không giống slide thuyết trình thô.
6. Không dùng JavaScript, không dùng external image, không dùng CDN, không dùng Google Fonts. Tự contained trong một file.
7. Không dùng CSS animation/transition động; frame tĩnh sắc nét.
8. Text không được tràn/đè nhau; dùng font Segoe UI / Arial / Noto Sans.
9. Trả về DUY NHẤT code HTML, không giải thích, không markdown.
"""

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Bạn là một motion/art director và senior HTML/CSS designer. "
                            "Bạn chỉ trả về HTML self-contained, sạch, render được ngay trong Chromium."
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
        """Inject robust Vietnamese font CSS into generated slides."""
        safe_css = """
    <style id="aivc-render-safety">
        *, *::before, *::after {
            box-sizing: border-box !important;
        }
        html, body, body *, .title, .subtitle {
            font-family: "Segoe UI", Arial, Tahoma, "Noto Sans", sans-serif !important;
            letter-spacing: 0 !important;
            text-rendering: geometricPrecision;
            -webkit-font-smoothing: antialiased;
            overflow-wrap: anywhere;
            word-break: normal;
            hyphens: auto;
        }
        body {
            width: """ + str(self.width) + """px !important;
            height: """ + str(self.height) + """px !important;
            margin: 0;
            overflow: hidden;
            padding: clamp(28px, 5vmin, 96px) !important;
        }
        body > * {
            max-width: 100% !important;
        }
        h1, .title {
            max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
            font-size: clamp(32px, min(7vw, 7vh), 92px) !important;
            line-height: 1.08 !important;
        }
        h2, h3 {
            max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
            font-size: clamp(24px, min(5vw, 5vh), 64px) !important;
            line-height: 1.15 !important;
        }
        p, .subtitle, li {
            max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
            font-size: clamp(18px, min(3.4vw, 3.4vh), 38px) !important;
            line-height: 1.45 !important;
        }
        img, video, svg, canvas {
            max-width: 100% !important;
            max-height: 100% !important;
        }
        .container, .content, .slide, .card, .panel, .animate {
            max-width: min(100%, calc(100vw - clamp(56px, 10vmin, 192px))) !important;
            max-height: calc(100vh - clamp(56px, 10vmin, 192px)) !important;
        }
    </style>
"""
        if "<meta charset" not in html.lower():
            html = re.sub(r"<head([^>]*)>", r'<head\1>\n    <meta charset="UTF-8">', html, count=1, flags=re.IGNORECASE)
        if "</head>" in html.lower():
            return re.sub(r"</head>", safe_css + "</head>", html, count=1, flags=re.IGNORECASE)
        return safe_css + html

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
    def render_slides_to_video(self, html_files: List[str], durations: Optional[List[int]] = None, resume: bool = False) -> List[str]:
        """
        Dùng Playwright headless để chụp frame PNG high-DPI,
        rồi tạo clip MP4 tĩnh theo thời lượng từng slide.
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
                    self._log(f"   🔁 Dùng lại video tĩnh đã render: {path}")
                self._log(f"✅ Đã dùng lại {len(cached_clips)} video clips")
                return cached_clips
        elif resume:
            self._log("   ℹ️ Cache video cũ không khớp phiên bản render tĩnh, sẽ render lại.")

        self._log("🎥 Khởi động Playwright để chụp frame tĩnh high-DPI...")

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
                    frame_path = os.path.join(frame_dir, f"slide_{slide_num}.png")

                    if resume and self._is_valid_file(final_video_path, min_size=1024):
                        video_clips.append(final_video_path)
                        self._log(f"   🔁 Dùng lại video cảnh {slide_num}: {final_video_path}")
                        continue

                    self._log(f"   🖼️ Render frame cảnh {slide_num}/{len(html_files)} ở {self.STATIC_FRAME_SCALE}x...")
                    shutil.rmtree(frame_dir, ignore_errors=True)
                    os.makedirs(frame_dir, exist_ok=True)

                    context = browser.new_context(
                        viewport={"width": self.width, "height": self.height},
                        device_scale_factor=self.STATIC_FRAME_SCALE,
                    )
                    try:
                        page = context.new_page()
                        file_url = Path(html_file).resolve().as_uri()
                        page.goto(file_url, wait_until="networkidle")
                        page.add_style_tag(content=self._static_render_css())
                        try:
                            page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true")
                        except Exception:
                            pass
                        time.sleep(0.25)
                        page.screenshot(
                            path=frame_path,
                            full_page=False,
                            scale="device",
                            animations="disabled",
                        )
                    finally:
                        context.close()

                    if self._write_static_frame_video(frame_path, final_video_path, duration):
                        video_clips.append(final_video_path)
                        self._log(f"   ✅ Đã render video tĩnh: {final_video_path}")

                    shutil.rmtree(frame_dir, ignore_errors=True)
            finally:
                browser.close()

        self._log(f"✅ Đã render xong {len(video_clips)} đoạn video tĩnh")
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
                        try:
                            page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true")
                        except Exception:
                            pass
                        time.sleep(0.15)
                        page.screenshot(
                            path=preview_path,
                            full_page=False,
                            scale="css",
                            animations="disabled",
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
