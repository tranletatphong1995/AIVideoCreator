"""
Module 2: Audio Agent
- Sử dụng VieNeu-TTS SDK (pip install vieneu)  
- Tạo file audio .wav cho từng lời thoại slide
- Hỗ trợ cả Standard mode (GGUF+ONNX, chất lượng cao) và Turbo mode (nhanh, CPU)
"""

import os
import subprocess
import sys
from typing import List, Optional
from pathlib import Path


class AudioAgent:
    """Agent tạo âm thanh tiếng Việt từ lời thoại slide bằng VieNeu-TTS SDK."""

    AUDIO_DIR = "temp_audio"

    def __init__(self, signals=None, mode: str = "standard", emotion: str = "natural"):
        """
        Args:
            signals: WorkerSignals từ UI
            mode: "standard" (chất lượng cao) hoặc "turbo" (nhanh, CPU)
            emotion: "natural" (tự nhiên) hoặc "storytelling" (kể chuyện)
        """
        self.signals = signals
        self.mode = mode
        self.emotion = emotion
        self.tts = None
        os.makedirs(self.AUDIO_DIR, exist_ok=True)

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
    def _is_valid_file(path: str, min_size: int = 44) -> bool:
        return os.path.exists(path) and os.path.getsize(path) >= min_size

    def _run_tts_worker(self, text: str, output_path: str, voice_id: Optional[str] = None, timeout_sec: int = 900) -> str:
        """Generate one wav file in a child process so native TTS crashes stay isolated."""
        worker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_worker.py")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [
            sys.executable,
            worker_path,
            "--mode",
            self.mode,
            "--text",
            text,
            "--output",
            output_path,
        ]
        if voice_id:
            cmd.extend(["--voice-id", voice_id])

        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"TTS worker failed with exit code {result.returncode}."
                + (f"\n{details}" if details else "")
            )
        if not self._is_valid_file(output_path):
            raise RuntimeError(f"TTS worker did not create a valid wav file: {output_path}")
        return output_path

    def test_tts_sample(self, text: str, voice_id: Optional[str] = None) -> str:
        """Create a short probe wav file before running expensive video steps."""
        output_path = os.path.join(self.AUDIO_DIR, "tts_test.wav")
        if os.path.exists(output_path):
            os.remove(output_path)
        self._log("🔊 Test TTS trước khi render video...")
        self._run_tts_worker(text, output_path, voice_id=voice_id, timeout_sec=900)
        self._log(f"✅ Test TTS thành công: {output_path}")
        return output_path

    # ──────────────────────────────────────
    # Kiểm tra & cài đặt VieNeu
    # ──────────────────────────────────────
    def _ensure_vieneu_installed(self) -> bool:
        """Kiểm tra và cài đặt VieNeu SDK nếu chưa có."""
        try:
            import vieneu
            self._log("✅ VieNeu-TTS SDK đã sẵn sàng")
            return True
        except ImportError:
            self._log("📦 Đang cài đặt VieNeu-TTS SDK...")
            try:
                # Cài đặt vieneu (có pre-built wheel cho Windows CPU)
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "vieneu",
                    "--extra-index-url", "https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._log("✅ Đã cài đặt VieNeu-TTS SDK thành công")
                return True
            except subprocess.CalledProcessError as e:
                self._log(f"❌ Lỗi cài đặt VieNeu: {e}")
                return False

    # ──────────────────────────────────────
    # Khởi tạo TTS engine
    # ──────────────────────────────────────
    def _init_tts(self):
        """Khởi tạo VieNeu TTS engine."""
        if self.tts is not None:
            return

        if not self._ensure_vieneu_installed():
            raise RuntimeError("Không thể cài đặt VieNeu-TTS. Hãy cài thủ công: pip install vieneu")

        from vieneu import Vieneu

        self._log(f"🔧 Khởi tạo VieNeu-TTS (mode={self.mode})...")

        if self.mode == "turbo":
            self.tts = Vieneu(mode="turbo")
            self._log("⚡ Đang dùng Turbo mode (CPU, tốc độ nhanh)")
        else:
            self.tts = Vieneu(mode="standard")
            self._log("🎯 Đang dùng Standard mode (chất lượng cao)")

        # Liệt kê giọng có sẵn
        try:
            voices = self.tts.list_preset_voices()
            self._log(f"🎤 Giọng nói có sẵn: {len(voices)} giọng")
            for desc, voice_id in voices[:5]:  # Hiển thị tối đa 5
                self._log(f"   🗣️ {desc} (ID: {voice_id})")
        except Exception:
            self._log("   ℹ️ Sử dụng giọng mặc định")

    # ──────────────────────────────────────
    # Clone Git repo (tùy chọn, cho advanced users)
    # ──────────────────────────────────────
    @staticmethod
    def clone_tts_repo(target_dir: str = "tts_engine") -> bool:
        """
        Clone VieNeu-TTS repo (tùy chọn, dành cho ai muốn chạy từ source).
        SDK pip install vieneu là cách khuyến nghị.
        """
        if os.path.exists(target_dir):
            print(f"📂 Thư mục {target_dir} đã tồn tại, bỏ qua clone.")
            return True

        try:
            print(f"📥 Đang clone VieNeu-TTS vào {target_dir}...")
            subprocess.check_call([
                "git", "clone",
                "https://github.com/pnnbao97/VieNeu-TTS.git",
                target_dir
            ])
            print(f"✅ Đã clone thành công vào {target_dir}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"❌ Lỗi clone repo: {e}")
            return False

    # ──────────────────────────────────────
    # Tạo audio cho từng slide
    # ──────────────────────────────────────
    def generate_audio(self, narrations: List[str], voice_id: Optional[str] = None, resume: bool = False) -> List[str]:
        """
        Tạo file audio .wav cho từng lời thoại.

        Args:
            narrations: Danh sách lời thoại tiếng Việt
            voice_id: ID giọng nói (None = giọng mặc định)

        Returns:
            Danh sách đường dẫn file .wav
        """
        audio_files = []
        expected_files = [
            os.path.join(self.AUDIO_DIR, f"audio_{idx + 1}.wav")
            for idx in range(len(narrations))
        ]
        if resume and expected_files and all(self._is_valid_file(path) for path in expected_files):
            for path in expected_files:
                self._log(f"   🔁 Dùng lại audio: {path}")
            self._log(f"✅ Đã dùng lại {len(expected_files)} file audio")
            return expected_files

        if not self._ensure_vieneu_installed():
            raise RuntimeError("Không thể cài đặt VieNeu-TTS. Hãy cài thủ công: pip install vieneu")

        voice_data = None

        # Lấy voice data nếu có chỉ định
        if voice_id:
            try:
                voice_data = self.tts.get_preset_voice(voice_id)
                self._log(f"🎤 Đang dùng giọng: {voice_id}")
            except Exception as e:
                self._log(f"⚠️ Không tìm thấy giọng '{voice_id}', dùng giọng mặc định: {e}")

        for idx, text in enumerate(narrations):
            slide_num = idx + 1
            output_path = os.path.join(self.AUDIO_DIR, f"audio_{slide_num}.wav")
            if resume and self._is_valid_file(output_path):
                audio_files.append(output_path)
                self._log(f"   🔁 Dùng lại audio slide {slide_num}: {output_path}")
                continue

            self._log(f"🔊 Tạo audio slide {slide_num}/{len(narrations)}...")
            self._log(f"   📝 \"{text[:80]}{'...' if len(text) > 80 else ''}\"")

            try:
                # Tạo audio bằng VieNeu SDK
                self._run_tts_worker(text, output_path, voice_id=voice_id)

                # Lưu file
                audio_files.append(output_path)
                self._log(f"   ✅ Đã lưu: {output_path}")

            except Exception as e:
                self._log(f"   ❌ Lỗi TTS slide {slide_num}: {e}")
                # Tạo file silence fallback
                silence_path = self._create_silence(slide_num, duration_sec=5)
                audio_files.append(silence_path)
                self._log(f"   🔇 Đã tạo file im lặng thay thế: {silence_path}")

        self._log(f"✅ Đã tạo xong {len(audio_files)} file audio")
        return audio_files

    def generate_audio_for_slide(
        self,
        text: str,
        slide_num: int,
        total_slides: int = 1,
        voice_id: Optional[str] = None,
        resume: bool = False,
    ) -> str:
        """Create or reuse one slide narration file."""
        output_path = os.path.join(self.AUDIO_DIR, f"audio_{slide_num}.wav")
        if resume and self._is_valid_file(output_path):
            self._log(f"   🔁 Dùng lại audio slide {slide_num}: {output_path}")
            return output_path

        if not self._ensure_vieneu_installed():
            raise RuntimeError("Không thể cài đặt VieNeu-TTS. Hãy cài thủ công: pip install vieneu")

        if voice_id:
            try:
                self.tts.get_preset_voice(voice_id)
                self._log(f"🎤 Đang dùng giọng: {voice_id}")
            except Exception as e:
                self._log(f"⚠️ Không tìm thấy giọng '{voice_id}', dùng giọng mặc định: {e}")

        self._log(f"🔊 Tạo audio slide {slide_num}/{total_slides}...")
        self._log(f"   📝 \"{text[:80]}{'...' if len(text) > 80 else ''}\"")
        try:
            self._run_tts_worker(text, output_path, voice_id=voice_id)
            self._log(f"   ✅ Đã lưu: {output_path}")
            return output_path
        except Exception as e:
            self._log(f"   ❌ Lỗi TTS slide {slide_num}: {e}")
            silence_path = self._create_silence(slide_num, duration_sec=5)
            self._log(f"   🔇 Đã tạo file im lặng thay thế: {silence_path}")
            return silence_path

    def _create_silence(self, slide_num: int, duration_sec: float = 5.0) -> str:
        """Tạo file WAV im lặng (fallback khi TTS lỗi)."""
        import struct
        import wave

        output_path = os.path.join(self.AUDIO_DIR, f"audio_{slide_num}.wav")
        sample_rate = 24000
        num_samples = int(sample_rate * duration_sec)

        with wave.open(output_path, 'w') as wav_file:
            wav_file.setnchannels(1)           # Mono
            wav_file.setsampwidth(2)           # 16-bit
            wav_file.setframerate(sample_rate)  # 24kHz (khớp VieNeu)
            # Ghi silence (toàn zero)
            wav_file.writeframes(struct.pack(f'{num_samples}h', *([0] * num_samples)))

        return output_path

    # ──────────────────────────────────────
    # Dọn dẹp
    # ──────────────────────────────────────
    def cleanup(self):
        """Dọn dẹp thư mục audio tạm."""
        import shutil
        if os.path.exists(self.AUDIO_DIR):
            shutil.rmtree(self.AUDIO_DIR, ignore_errors=True)
            self._log("🧹 Đã dọn dẹp thư mục audio tạm")
