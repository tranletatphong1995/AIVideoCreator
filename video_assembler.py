"""
Module 3: Video Assembler
- Ghép slide video (.webm/.mp4) + audio (.wav) thành từng đoạn
- Điều chỉnh độ dài video khớp với audio
- Nối tất cả đoạn thành file final_output.mp4
"""

import os
import shutil
import sys
from typing import List, Optional, Tuple

from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    concatenate_videoclips,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    vfx,
)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:  # pragma: no cover - MoviePy normally installs Pillow.
    Image = ImageDraw = ImageFont = ImageFilter = None


class VideoAssembler:
    """Ghép video slides + audio thành video hoàn chỉnh."""

    TEMP_MERGE_DIR = "temp_merged"

    def __init__(self, signals=None):
        self.signals = signals
        os.makedirs(self.TEMP_MERGE_DIR, exist_ok=True)

    def _log(self, msg: str):
        if self.signals:
            self.signals.log_message.emit(msg)
        try:
            print(msg)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            print(msg.encode(encoding, errors="replace").decode(encoding))

    def _concat_without_transitions(self, clips: List[VideoFileClip]):
        return concatenate_videoclips(clips, method="compose")


    def _bitrate_for_size(self, size, intermediate: bool = False) -> str:
        """Pick a sane bitrate from output pixel count to avoid soft text."""
        width, height = size
        pixels = width * height
        if pixels >= 3840 * 2160:
            mbps = 48
        elif pixels >= 2560 * 1440:
            mbps = 28
        elif pixels >= 1920 * 1080:
            mbps = 16
        elif pixels >= 1080 * 1350:
            mbps = 14
        elif pixels >= 1080 * 1080:
            mbps = 12
        else:
            mbps = 8
        if intermediate:
            mbps = int(mbps * 1.25)
        return f"{mbps}M"

    def _ffmpeg_quality_params(self) -> list:
        return [
            "-crf", "14",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ]

    # ──────────────────────────────────────
    # Ghép 1 slide video + audio
    # ──────────────────────────────────────
    def _merge_single(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """
        Ghép 1 file video + 1 file audio.
        Điều chỉnh video duration khớp audio duration.
        """
        video_clip = None
        audio_clip = None
        final_clip = None

        try:
            audio_clip = AudioFileClip(audio_path)
            audio_duration = audio_clip.duration
            self._log(f"   🔊 Audio duration: {audio_duration:.1f}s")

            # Mở video clip
            video_clip = VideoFileClip(video_path)
            video_duration = video_clip.duration
            self._log(f"   🎥 Video duration: {video_duration:.1f}s")

            # Điều chỉnh video duration khớp audio
            if video_duration < audio_duration:
                # Video ngắn hơn audio → lặp lại hoặc freeze frame cuối
                self._log(f"   🔄 Video ngắn hơn audio, freeze frame cuối...")
                # Freeze frame cuối cùng để kéo dài
                last_frame_time = max(0, video_duration - 0.05)
                last_frame = video_clip.get_frame(last_frame_time)
                freeze_clip = ImageClip(last_frame).with_duration(
                    audio_duration - video_duration
                ).with_fps(24)
                video_clip = concatenate_videoclips([video_clip, freeze_clip])
            elif video_duration > audio_duration:
                # Video dài hơn audio → cắt bớt
                self._log(f"   ✂️ Video dài hơn audio, cắt bớt...")
                video_clip = video_clip.subclipped(0, audio_duration)

            # Ghép audio vào video
            final_clip = video_clip.with_audio(audio_clip)

            # Xuất file
            final_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                logger=None,
                threads=4,
                preset="medium",
                bitrate=self._bitrate_for_size(final_clip.size, intermediate=True),
                ffmpeg_params=self._ffmpeg_quality_params()
            )

            self._log(f"   ✅ Đã ghép: {output_path} ({audio_duration:.1f}s)")
            return True

        except Exception as e:
            self._log(f"   ❌ Lỗi ghép: {e}")
            return False

        finally:
            # Giải phóng tài nguyên
            if final_clip:
                try:
                    final_clip.close()
                except Exception:
                    pass
            if video_clip:
                try:
                    video_clip.close()
                except Exception:
                    pass
            if audio_clip:
                try:
                    audio_clip.close()
                except Exception:
                    pass

    # ──────────────────────────────────────
    # Tạo video từ audio + ảnh tĩnh (fallback)
    # ──────────────────────────────────────
    def _create_from_audio_only(self, audio_path: str, output_path: str, 
                                 bg_color: tuple = (26, 26, 46)) -> bool:
        """Tạo video với background color + audio (khi không có video clip)."""
        audio_clip = None
        color_clip = None
        final_clip = None

        try:
            audio_clip = AudioFileClip(audio_path)
            color_clip = ColorClip(
                size=(1280, 720),
                color=bg_color,
                duration=audio_clip.duration
            )
            final_clip = color_clip.with_audio(audio_clip)

            final_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                logger=None,
                threads=4,
                preset="medium",
                bitrate=self._bitrate_for_size(final_clip.size, intermediate=True),
                ffmpeg_params=self._ffmpeg_quality_params()
            )
            return True

        except Exception as e:
            self._log(f"   ❌ Lỗi tạo video từ audio: {e}")
            return False

        finally:
            for clip in [final_clip, color_clip, audio_clip]:
                if clip:
                    try:
                        clip.close()
                    except Exception:
                        pass

    # ──────────────────────────────────────
    # Pipeline chính: ghép tất cả
    # ──────────────────────────────────────
    def assemble(self, video_clips: List[str], audio_files: List[str], 
                 output_path: str, bg_music_path: Optional[str] = None,
                 bg_music_volume: float = 0.2) -> str:
        """
        Ghép tất cả slides thành 1 video hoàn chỉnh.
        
        Args:
            video_clips: Danh sách file video (.webm/.mp4) cho mỗi slide
            audio_files: Danh sách file audio (.wav) cho mỗi slide
            output_path: Đường dẫn file output cuối cùng
            bg_music_path: Đường dẫn file nhạc nền (None = không có)
            bg_music_volume: Âm lượng nhạc nền (0.0 - 1.0, mặc định 0.2 = 20%)

        Returns:
            Đường dẫn file output
        """
        self._log("🔧 Bắt đầu ghép video...")

        # Đảm bảo thư mục output tồn tại
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        merged_parts = []
        num_parts = max(len(video_clips), len(audio_files))

        for i in range(num_parts):
            slide_num = i + 1
            self._log(f"📎 Ghép phần {slide_num}/{num_parts}...")

            merged_path = os.path.join(self.TEMP_MERGE_DIR, f"part_{slide_num}.mp4")
            video_path = video_clips[i] if i < len(video_clips) else None
            audio_path = audio_files[i] if i < len(audio_files) else None

            if video_path and audio_path and os.path.exists(video_path) and os.path.exists(audio_path):
                # Có cả video lẫn audio → ghép
                success = self._merge_single(video_path, audio_path, merged_path)
            elif audio_path and os.path.exists(audio_path):
                # Chỉ có audio → tạo video với background
                self._log(f"   ⚠️ Không có video cho slide {slide_num}, tạo từ audio...")
                success = self._create_from_audio_only(audio_path, merged_path)
            elif video_path and os.path.exists(video_path):
                # Chỉ có video → copy nguyên
                self._log(f"   ⚠️ Không có audio cho slide {slide_num}")
                try:
                    clip = VideoFileClip(video_path)
                    clip.write_videofile(merged_path, codec="libx264", audio=False, 
                                       fps=30, logger=None, preset="medium",
                                       bitrate=self._bitrate_for_size(clip.size, intermediate=True),
                                       ffmpeg_params=self._ffmpeg_quality_params())
                    clip.close()
                    success = True
                except Exception as e:
                    self._log(f"   ❌ Lỗi: {e}")
                    success = False
            else:
                self._log(f"   ⚠️ Không có file nào cho slide {slide_num}, bỏ qua")
                continue

            if success and os.path.exists(merged_path):
                merged_parts.append(merged_path)

        if not merged_parts:
            raise RuntimeError("Không có phần video nào được tạo thành công!")

        # ── Nối tất cả thành 1 video ──
        self._log(f"🎬 Nối {len(merged_parts)} phần thành video cuối cùng...")

        clips = []
        try:
            for part in merged_parts:
                clips.append(VideoFileClip(part))

            final = self._concat_without_transitions(clips)

            # ── Mix nhạc nền nếu có ──
            if bg_music_path and os.path.exists(bg_music_path):
                final = self._mix_background_music(
                    final, bg_music_path, bg_music_volume
                )

            final.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                threads=4,
                preset="slow",
                bitrate=self._bitrate_for_size(final.size),
                ffmpeg_params=self._ffmpeg_quality_params(),
                logger=None
            )

            total_duration = final.duration
            final.close()

            self._log(f"🎉 Video hoàn chỉnh: {output_path}")
            self._log(f"   ⏱️ Thời lượng: {total_duration:.1f} giây")
            self._log(f"   📊 Số phần: {len(merged_parts)}")

            # Lấy kích thước file
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            self._log(f"   💾 Kích thước: {file_size:.1f} MB")

            return output_path

        except Exception as e:
            self._log(f"❌ Lỗi nối video: {e}")
            raise

        finally:
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass

    # ──────────────────────────────────────
    # Dựng video từ ảnh minh họa + subtitle + audio
    # ──────────────────────────────────────
    def assemble_image_story(
        self,
        image_files: List[str],
        audio_files: List[str],
        subtitle_cues_by_slide: List[list],
        output_path: str,
        resolution: Tuple[int, int] = (1280, 720),
        bg_music_path: Optional[str] = None,
        bg_music_volume: float = 0.2,
    ) -> str:
        """
        Dựng video chỉ gồm ảnh minh họa, subtitle timed cues và âm thanh.
        Fooocus ảnh là nền; subtitle được overlay động theo start/end frame.
        """
        if Image is None:
            raise RuntimeError("Thiếu Pillow. Hãy cài: python -m pip install Pillow")

        self._log("🖼️ Bắt đầu dựng video ảnh minh họa + subtitle + audio...")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        os.makedirs(self.TEMP_MERGE_DIR, exist_ok=True)

        merged_parts = []
        num_parts = min(len(image_files), len(audio_files))
        if num_parts == 0:
            raise RuntimeError("Không có đủ ảnh/audio để dựng video ảnh minh họa.")

        for idx in range(num_parts):
            slide_num = idx + 1
            image_path = image_files[idx]
            audio_path = audio_files[idx]
            subtitle_cues = subtitle_cues_by_slide[idx] if idx < len(subtitle_cues_by_slide) else []
            frame_path = os.path.join(self.TEMP_MERGE_DIR, f"image_story_bg_{slide_num}.png")
            part_path = os.path.join(self.TEMP_MERGE_DIR, f"image_story_part_{slide_num}.mp4")

            if not os.path.exists(image_path):
                self._log(f"   ⚠️ Không tìm thấy ảnh cảnh {slide_num}: {image_path}")
                continue
            if not os.path.exists(audio_path):
                self._log(f"   ⚠️ Không tìm thấy audio cảnh {slide_num}: {audio_path}")
                continue

            self._log(f"📎 Dựng cảnh ảnh {slide_num}/{num_parts}...")
            self._compose_image_background_frame(image_path, frame_path, resolution)
            if self._write_image_part(frame_path, audio_path, part_path, resolution, subtitle_cues):
                merged_parts.append(part_path)

        if not merged_parts:
            raise RuntimeError("Không có phần video ảnh minh họa nào được tạo thành công.")

        clips = []
        final = None
        try:
            for part in merged_parts:
                clips.append(VideoFileClip(part))

            final = self._concat_without_transitions(clips)
            if bg_music_path and os.path.exists(bg_music_path):
                final = self._mix_background_music(final, bg_music_path, bg_music_volume)

            final.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                threads=4,
                preset="slow",
                bitrate=self._bitrate_for_size(final.size),
                ffmpeg_params=self._ffmpeg_quality_params(),
                logger=None,
            )

            duration = final.duration
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            self._log(f"🎉 Video ảnh minh họa hoàn chỉnh: {output_path}")
            self._log(f"   ⏱️ Thời lượng: {duration:.1f} giây")
            self._log(f"   💾 Kích thước: {file_size:.1f} MB")
            return output_path

        finally:
            if final:
                try:
                    final.close()
                except Exception:
                    pass
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass

    def _write_image_part(
        self,
        frame_path: str,
        audio_path: str,
        output_path: str,
        resolution: Tuple[int, int],
        subtitle_cues: Optional[list] = None,
    ) -> bool:
        audio_clip = None
        base_clip = None
        final_clip = None
        overlay_clips = []
        try:
            audio_clip = AudioFileClip(audio_path)
            duration = audio_clip.duration
            base_clip = ImageClip(frame_path).with_duration(duration).with_fps(30)
            video_layers = [base_clip]
            normalized_cues = self._normalize_subtitle_cues(subtitle_cues or [], duration)

            for cue_index, cue in enumerate(normalized_cues, start=1):
                overlay_path = os.path.join(
                    self.TEMP_MERGE_DIR,
                    f"{os.path.splitext(os.path.basename(output_path))[0]}_subtitle_{cue_index}.png",
                )
                self._compose_subtitle_overlay(cue["text"], overlay_path, resolution)
                cue_duration = max(0.05, cue["end"] - cue["start"])
                overlay_clip = (
                    ImageClip(overlay_path, transparent=True)
                    .with_start(cue["start"])
                    .with_duration(cue_duration)
                    .with_fps(30)
                )
                fade_duration = min(0.12, cue_duration / 3)
                if fade_duration > 0.03:
                    overlay_clip = overlay_clip.with_effects([
                        vfx.FadeIn(fade_duration),
                        vfx.FadeOut(fade_duration),
                    ])
                overlay_clips.append(overlay_clip)
                video_layers.append(overlay_clip)

            final_clip = CompositeVideoClip(video_layers, size=resolution).with_audio(audio_clip)
            final_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                logger=None,
                threads=4,
                preset="medium",
                bitrate=self._bitrate_for_size(resolution, intermediate=True),
                ffmpeg_params=self._ffmpeg_quality_params(),
            )
            self._log(f"   ✅ Đã dựng cảnh ảnh: {output_path} ({audio_clip.duration:.1f}s)")
            return True
        except Exception as e:
            self._log(f"   ❌ Lỗi dựng cảnh ảnh: {e}")
            return False
        finally:
            for clip in [final_clip, base_clip, *overlay_clips, audio_clip]:
                if clip:
                    try:
                        clip.close()
                    except Exception:
                        pass

    def _compose_image_background_frame(
        self,
        image_path: str,
        output_path: str,
        resolution: Tuple[int, int],
    ):
        width, height = resolution
        source = Image.open(image_path).convert("RGB")
        canvas = self._cover_image(source, width, height)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        gradient_top = int(height * 0.56)
        for y in range(gradient_top, height):
            alpha = int(18 + 132 * ((y - gradient_top) / max(1, height - gradient_top)) ** 1.35)
            overlay_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
        canvas.convert("RGB").save(output_path, quality=96)

    def _normalize_subtitle_cues(self, cues: list, audio_duration: float) -> List[dict]:
        normalized = []
        cursor = 0.0
        duration = max(0.1, float(audio_duration))
        for raw in cues:
            if hasattr(raw, "model_dump"):
                raw = raw.model_dump()
            elif not isinstance(raw, dict):
                raw = {
                    "start": getattr(raw, "start", cursor),
                    "end": getattr(raw, "end", cursor + 1.0),
                    "text": getattr(raw, "text", ""),
                }

            text = str(raw.get("text", "") or "").strip()
            if not text:
                continue
            try:
                start = float(raw.get("start", cursor))
            except Exception:
                start = cursor
            try:
                end = float(raw.get("end", start + 1.0))
            except Exception:
                end = start + 1.0

            start = max(cursor, min(start, duration))
            end = max(start + 0.05, min(end, duration))
            if start >= duration:
                break
            normalized.append({"start": start, "end": end, "text": text})
            cursor = end
        return normalized

    def _compose_subtitle_overlay(
        self,
        subtitle: str,
        output_path: str,
        resolution: Tuple[int, int],
    ):
        width, height = resolution
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        margin_x = max(44, int(width * 0.055))
        bottom_margin = max(48, int(height * 0.07))
        max_text_width = width - margin_x * 2
        font = self._subtitle_font(width, bold=True)
        lines = self._wrap_text(draw, subtitle, font, max_text_width, max_lines=2)

        while lines and self._text_block_height(draw, lines, font) > height * 0.22 and font.size > 28:
            font = self._load_font(font.size - 4, bold=True)
            lines = self._wrap_text(draw, subtitle, font, max_text_width, max_lines=2)

        if not lines:
            canvas.save(output_path)
            return

        line_gap = int(font.size * 0.22)
        line_height = self._line_height(font)
        block_height = line_height * len(lines) + max(0, len(lines) - 1) * line_gap
        box_pad_x = max(24, int(width * 0.024))
        box_pad_y = max(18, int(height * 0.018))
        box_top = height - bottom_margin - block_height - box_pad_y * 2
        box_bottom = height - bottom_margin
        box_left = margin_x - box_pad_x
        box_right = width - margin_x + box_pad_x

        draw.rounded_rectangle(
            (box_left, box_top, box_right, box_bottom),
            radius=max(10, int(height * 0.012)),
            fill=(6, 10, 18, 205),
            outline=(255, 255, 255, 42),
            width=1,
        )

        accent_width = max(5, int(width * 0.004))
        draw.rounded_rectangle(
            (box_left, box_top + box_pad_y, box_left + accent_width, box_bottom - box_pad_y),
            radius=accent_width,
            fill=(56, 189, 248, 235),
        )

        y = box_top + box_pad_y
        inner_width = box_right - box_left - box_pad_x * 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = box_left + box_pad_x + max(0, (inner_width - text_width) // 2)
            stroke = max(2, int(font.size * 0.055))
            draw.text(
                (x, y),
                line,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=stroke,
                stroke_fill=(0, 0, 0, 220),
            )
            y += line_height + line_gap

        canvas.save(output_path)

    def _compose_subtitle_frame(
        self,
        image_path: str,
        subtitle: str,
        output_path: str,
        resolution: Tuple[int, int],
    ):
        width, height = resolution
        source = Image.open(image_path).convert("RGB")
        canvas = self._cover_image(source, width, height)

        # Add a gentle dark lower gradient so subtitles stay readable on busy art.
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        gradient_top = int(height * 0.56)
        for y in range(gradient_top, height):
            alpha = int(22 + 150 * ((y - gradient_top) / max(1, height - gradient_top)) ** 1.4)
            overlay_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

        draw = ImageDraw.Draw(canvas)
        margin_x = max(44, int(width * 0.055))
        bottom_margin = max(48, int(height * 0.07))
        max_text_width = width - margin_x * 2
        font = self._subtitle_font(width, bold=True)
        lines = self._wrap_text(draw, subtitle, font, max_text_width, max_lines=4)

        while lines and self._text_block_height(draw, lines, font) > height * 0.28 and font.size > 28:
            font = self._load_font(font.size - 4, bold=True)
            lines = self._wrap_text(draw, subtitle, font, max_text_width, max_lines=4)

        line_height = self._line_height(font)
        block_height = line_height * len(lines) + max(0, len(lines) - 1) * int(font.size * 0.22)
        box_pad_x = max(24, int(width * 0.024))
        box_pad_y = max(18, int(height * 0.018))
        box_top = height - bottom_margin - block_height - box_pad_y * 2
        box_bottom = height - bottom_margin
        box_left = margin_x - box_pad_x
        box_right = width - margin_x + box_pad_x

        box = Image.new("RGBA", (box_right - box_left, box_bottom - box_top), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box)
        box_draw.rounded_rectangle(
            (0, 0, box.width - 1, box.height - 1),
            radius=max(10, int(height * 0.012)),
            fill=(6, 10, 18, 190),
            outline=(255, 255, 255, 38),
            width=1,
        )
        box = box.filter(ImageFilter.GaussianBlur(radius=0.2))
        canvas.alpha_composite(box, (box_left, box_top))

        accent_width = max(5, int(width * 0.004))
        draw.rounded_rectangle(
            (box_left, box_top + box_pad_y, box_left + accent_width, box_bottom - box_pad_y),
            radius=accent_width,
            fill=(56, 189, 248, 230),
        )

        y = box_top + box_pad_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = box_left + box_pad_x + max(0, (box.width - box_pad_x * 2 - text_width) // 2)
            stroke = max(2, int(font.size * 0.055))
            draw.text(
                (x, y),
                line,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=stroke,
                stroke_fill=(0, 0, 0, 210),
            )
            y += line_height + int(font.size * 0.22)

        canvas.convert("RGB").save(output_path, quality=96)

    def _cover_image(self, image, width: int, height: int):
        src_w, src_h = image.size
        scale = max(width / src_w, height / src_h)
        resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        return resized.crop((left, top, left + width, top + height))

    def _subtitle_font(self, width: int, bold: bool = True):
        size = max(34, min(72, int(width * 0.044)))
        return self._load_font(size, bold=bold)

    def _load_font(self, size: int, bold: bool = True):
        candidates = []
        if sys.platform.startswith("win"):
            candidates.extend([
                r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
                r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
            ])
        candidates.extend(["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arial.ttf"])

        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _wrap_text(self, draw, text: str, font, max_width: int, max_lines: int = 4) -> List[str]:
        words = (text or "").strip().split()
        if not words:
            return []

        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
                if len(lines) >= max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)

        if len(lines) == max_lines and len(" ".join(lines).split()) < len(words):
            lines[-1] = lines[-1].rstrip(" .,!?:;") + "..."
        return lines

    def _line_height(self, font) -> int:
        try:
            bbox = font.getbbox("Ag")
            return max(font.size, bbox[3] - bbox[1] + int(font.size * 0.22))
        except Exception:
            return int(font.size * 1.25)

    def _text_block_height(self, draw, lines: List[str], font) -> int:
        if not lines:
            return 0
        return self._line_height(font) * len(lines) + int(font.size * 0.22) * (len(lines) - 1)

    # ──────────────────────────────────────
    # Mix nhạc nền
    # ──────────────────────────────────────
    def _mix_background_music(self, video_clip, music_path: str, 
                               volume: float = 0.2):
        """
        Mix nhạc nền vào video. Nhạc sẽ được loop nếu ngắn hơn video,
        và giảm volume để không lấn át giọng nói.
        
        Args:
            video_clip: MoviePy VideoClip đã có audio narration
            music_path: Đường dẫn file nhạc nền
            volume: Âm lượng nhạc nền (0.0 - 1.0)
        """
        music_clip = None
        try:
            self._log(f"🎵 Đang mix nhạc nền: {os.path.basename(music_path)}")
            self._log(f"   🔉 Volume: {int(volume * 100)}%")

            music_clip = AudioFileClip(music_path)
            video_duration = video_clip.duration

            # Loop nhạc nếu ngắn hơn video
            if music_clip.duration < video_duration:
                loops_needed = int(video_duration / music_clip.duration) + 1
                self._log(f"   🔄 Nhạc ({music_clip.duration:.1f}s) ngắn hơn video ({video_duration:.1f}s), loop {loops_needed} lần")
                from moviepy import concatenate_audioclips
                music_clips = [music_clip] * loops_needed
                music_clip = concatenate_audioclips(music_clips)
            
            # Cắt nhạc cho khớp video
            music_clip = music_clip.subclipped(0, video_duration)
            
            # Giảm volume nhạc nền
            music_clip = music_clip.with_volume_scaled(volume)

            # Mix narration + nhạc nền
            original_audio = video_clip.audio
            if original_audio:
                mixed_audio = CompositeAudioClip([original_audio, music_clip])
                result = video_clip.with_audio(mixed_audio)
                self._log(f"   ✅ Đã mix nhạc nền thành công")
                return result
            else:
                # Không có narration, chỉ có nhạc nền
                result = video_clip.with_audio(music_clip)
                self._log(f"   ✅ Đã thêm nhạc nền (không có narration)")
                return result

        except Exception as e:
            self._log(f"   ⚠️ Lỗi mix nhạc nền: {e}")
            self._log(f"   ℹ️ Video sẽ giữ nguyên audio gốc (chỉ narration)")
            return video_clip
        finally:
            # Không close music_clip vì nó đang được dùng trong composite
            pass

    # ──────────────────────────────────────
    # Dọn dẹp
    # ──────────────────────────────────────
    def cleanup(self):
        """Dọn dẹp thư mục tạm."""
        if os.path.exists(self.TEMP_MERGE_DIR):
            shutil.rmtree(self.TEMP_MERGE_DIR, ignore_errors=True)
            self._log("🧹 Đã dọn dẹp thư mục merge tạm")
