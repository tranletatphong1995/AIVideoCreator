"""
Ollama subtitle agent.

Creates frame-timed subtitle cues from narration and real TTS audio duration.
Fooocus images stay text-free; subtitles are rendered later by VideoAssembler.
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from moviepy import AudioFileClip
from pydantic import BaseModel, Field

from module_ai_providers import LocalOllamaTextProvider


class SubtitleCue(BaseModel):
    """One subtitle cue in both seconds and frame indexes."""

    start: float = Field(default=0.0)
    end: float = Field(default=0.0)
    start_frame: int = Field(default=0)
    end_frame: int = Field(default=0)
    text: str = Field(default="")


class SubtitleAgent:
    """Generate readable subtitle cues with Ollama, with deterministic fallback."""

    TEMP_DIR = "temp_slides"
    CACHE_PATH = os.path.join(TEMP_DIR, "subtitles.json")
    MAX_CHARS_PER_CUE = 64
    MIN_CUE_DURATION = 0.65

    def __init__(
        self,
        model_name: str,
        signals=None,
        fps: int = 30,
        output_language: str = "vi",
        resolution: tuple = (1280, 720),
        text_provider=None,
        ai_mode: str = "local",
    ):
        self.model_name = model_name
        self.ai_mode = ai_mode or "local"
        self.text_provider = text_provider or LocalOllamaTextProvider(model_name)
        self.signals = signals
        self.fps = max(1, int(fps or 30))
        self.output_language = output_language if output_language in {"vi", "en"} else "vi"
        self.width, self.height = resolution
        os.makedirs(self.TEMP_DIR, exist_ok=True)

    def _log(self, msg: str):
        if self.signals:
            self.signals.log_message.emit(msg)
        try:
            print(msg)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            print(msg.encode(encoding, errors="replace").decode(encoding))

    def _language_name(self) -> str:
        return "Vietnamese" if self.output_language == "vi" else "English"

    def _audio_duration(self, audio_path: str) -> float:
        clip = None
        try:
            clip = AudioFileClip(audio_path)
            return max(0.1, float(clip.duration))
        finally:
            if clip:
                try:
                    clip.close()
                except Exception:
                    pass

    def _cache_meta(self, slide_count: int, durations: List[float]) -> dict:
        rounded = [round(float(duration), 2) for duration in durations]
        return {
            "version": 1,
            "fps": self.fps,
            "model_name": self.model_name,
            "ai_mode": self.ai_mode,
            "output_language": self.output_language,
            "resolution": [self.width, self.height],
            "slide_count": slide_count,
            "audio_durations": rounded,
        }

    def _load_cache(self, slide_count: int, durations: List[float]):
        try:
            with open(self.CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("meta") != self._cache_meta(slide_count, durations):
                return None
            slides = data.get("slides", [])
            if len(slides) != slide_count:
                return None
            return [
                [SubtitleCue(**cue) for cue in slide_cues]
                for slide_cues in slides
            ]
        except Exception:
            return None

    def _write_cache(self, cues_by_slide: List[List[SubtitleCue]], durations: List[float]):
        with open(self.CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "meta": self._cache_meta(len(cues_by_slide), durations),
                    "slides": [
                        [cue.model_dump() for cue in slide_cues]
                        for slide_cues in cues_by_slide
                    ],
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _extract_json(self, text: str):
        patterns = [
            r"```json\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
            r"(\[.*\])",
            r"(\{.*\})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
        return json.loads(text)

    def generate_for_plan(self, plan, audio_files: List[str], resume: bool = False, max_workers: int = 1) -> List[List[SubtitleCue]]:
        slides = list(getattr(plan, "slides", []) or [])
        durations = [
            self._audio_duration(audio_files[idx])
            for idx in range(min(len(slides), len(audio_files)))
        ]
        if len(durations) != len(slides):
            raise RuntimeError("Không đủ audio để tạo subtitle theo từng cảnh.")

        if resume:
            cached = self._load_cache(len(slides), durations)
            if cached:
                self._log(f"🔁 Dùng lại subtitle cache: {self.CACHE_PATH}")
                return cached
        if max(1, int(max_workers or 1)) > 1:
            return self._generate_for_plan_parallel(slides, durations, max_workers)

        all_cues = []
        self._log(f"💬 Tạo subtitle timed cues bằng Ollama ({self.fps}fps)...")
        for idx, slide in enumerate(slides, start=1):
            duration = durations[idx - 1]
            self._log(f"   💬 Subtitle cảnh {idx}/{len(slides)} ({duration:.1f}s)")
            all_cues.append(self.generate_for_slide(slide, duration))

        self._write_cache(all_cues, durations)
        self._log(f"✅ Đã lưu subtitle cache: {self.CACHE_PATH}")
        return all_cues

    def _generate_for_plan_parallel(self, slides, durations: List[float], max_workers: int) -> List[List[SubtitleCue]]:
        workers = max(1, int(max_workers or 1))
        all_cues = [None] * len(slides)
        self._log(f"⚡ Tạo subtitle song song với {workers} workers...")

        def generate_one(item):
            idx, slide = item
            duration = durations[idx]
            self._log(f"   💬 Subtitle cảnh {idx + 1}/{len(slides)} ({duration:.1f}s)")
            return idx, self.generate_for_slide(slide, duration)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(generate_one, item) for item in enumerate(slides)]
            for future in as_completed(futures):
                idx, cues = future.result()
                all_cues[idx] = cues

        all_cues = [cues or [] for cues in all_cues]
        self._write_cache(all_cues, durations)
        self._log(f"✅ Đã lưu subtitle cache: {self.CACHE_PATH}")
        return all_cues

    def generate_for_slide(self, slide, audio_duration: float) -> List[SubtitleCue]:
        narration = str(getattr(slide, "narration", "") or "").strip()
        if not narration:
            return []

        prompt = f"""Create subtitle cues for one video scene.

Language: {self._language_name()}
Audio duration: {audio_duration:.3f} seconds
FPS: {self.fps}
Resolution: {self.width}x{self.height}

Narration:
{narration}

Rules:
- Return ONLY valid JSON, no markdown.
- JSON shape: [{{"start": 0.0, "end": 1.8, "text": "..."}}]
- Keep each cue short and readable, max about {self.MAX_CHARS_PER_CUE} characters.
- Each cue should fit at most 2 subtitle lines.
- Preserve meaning, but you may shorten filler words.
- Cues must be chronological, non-overlapping, and cover most of the audio.
- First cue should start at 0.0. Last cue must end at {audio_duration:.3f} or earlier.
"""

        try:
            response = self.text_provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise video subtitle editor. Return clean machine-readable JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.25, "num_predict": 2048},
            )
            raw = response["message"]["content"]
            data = self._extract_json(raw)
            cues = self._coerce_json_cues(data)
            validated = self._validate_cues(cues, narration, audio_duration)
            if validated:
                return validated
        except Exception as e:
            self._log(f"   ⚠️ Ollama subtitle lỗi, dùng fallback: {e}")

        return self._fallback_cues(narration, audio_duration)

    def _coerce_json_cues(self, data) -> List[dict]:
        if isinstance(data, dict):
            if isinstance(data.get("subtitles"), list):
                return data["subtitles"]
            if isinstance(data.get("cues"), list):
                return data["cues"]
        if isinstance(data, list):
            return data
        return []

    def _validate_cues(self, raw_cues: List[dict], narration: str, audio_duration: float) -> List[SubtitleCue]:
        cues = []
        cursor = 0.0
        max_end = max(0.1, float(audio_duration))

        for raw in raw_cues:
            if not isinstance(raw, dict):
                continue
            text = self._clean_text(str(raw.get("text", "") or ""))
            if not text:
                continue
            start = self._safe_float(raw.get("start"), cursor)
            end = self._safe_float(raw.get("end"), start + self.MIN_CUE_DURATION)
            start = max(cursor, min(start, max_end))
            end = max(start + 0.25, min(end, max_end))
            if start >= max_end:
                break

            chunks = self._split_long_text(text)
            chunk_duration = max(self.MIN_CUE_DURATION, (end - start) / max(1, len(chunks)))
            for chunk in chunks:
                chunk_end = min(max_end, start + chunk_duration)
                if chunk_end - start >= 0.25:
                    cues.append(self._make_cue(start, chunk_end, chunk))
                start = chunk_end
                cursor = chunk_end
                if cursor >= max_end:
                    break

        if not cues:
            return self._fallback_cues(narration, audio_duration)

        if cues[-1].end < max_end - 0.5:
            cues[-1] = self._make_cue(cues[-1].start, max_end, cues[-1].text)

        return cues

    def _safe_float(self, value, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _make_cue(self, start: float, end: float, text: str) -> SubtitleCue:
        start = max(0.0, float(start))
        end = max(start + 0.25, float(end))
        start_frame = int(round(start * self.fps))
        end_frame = max(start_frame + 1, int(round(end * self.fps)))
        return SubtitleCue(
            start=start_frame / self.fps,
            end=end_frame / self.fps,
            start_frame=start_frame,
            end_frame=end_frame,
            text=self._clean_text(text),
        )

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return text.strip("\"'“”‘’")

    def _split_sentences(self, text: str) -> List[str]:
        parts = re.split(r"(?<=[.!?。！？])\s+|(?<=[,;:])\s+", text.strip())
        sentences = [self._clean_text(part) for part in parts if self._clean_text(part)]
        return sentences or [self._clean_text(text)]

    def _split_long_text(self, text: str) -> List[str]:
        text = self._clean_text(text)
        if len(text) <= self.MAX_CHARS_PER_CUE:
            return [text]

        words = text.split()
        chunks = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= self.MAX_CHARS_PER_CUE or not current:
                current = candidate
            else:
                chunks.append(current)
                current = word
        if current:
            chunks.append(current)
        return chunks

    def _fallback_cues(self, narration: str, audio_duration: float) -> List[SubtitleCue]:
        pieces = []
        for sentence in self._split_sentences(narration):
            pieces.extend(self._split_long_text(sentence))
        pieces = [piece for piece in pieces if piece]
        if not pieces:
            return []

        weights = [max(1, len(piece)) for piece in pieces]
        total_weight = sum(weights)
        cursor = 0.0
        cues = []
        duration = max(0.1, float(audio_duration))

        for idx, piece in enumerate(pieces):
            if idx == len(pieces) - 1:
                end = duration
            else:
                share = duration * (weights[idx] / total_weight)
                end = min(duration, cursor + max(self.MIN_CUE_DURATION, share))
            if end <= cursor:
                end = min(duration, cursor + self.MIN_CUE_DURATION)
            cues.append(self._make_cue(cursor, end, piece))
            cursor = end
            if cursor >= duration:
                break

        return cues


if __name__ == "__main__":
    sample = "Đây là câu đầu tiên. Đây là câu thứ hai dài hơn một chút để kiểm tra chia phụ đề."
    agent = SubtitleAgent("dummy")
    for cue in agent._fallback_cues(sample, 5.0):
        print(cue.model_dump())
