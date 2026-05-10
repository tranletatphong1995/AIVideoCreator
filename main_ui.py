"""
AIVideoCreator - Main UI
Giao diện chính sử dụng PyQt5 để tạo video AI tự động.
Pipeline: Brainstorming → Coding HTML → Rendering → Audio TTS → Merging
"""

import sys
import os
import threading
import json
import subprocess
import time
from datetime import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))
qt_plugins_dir = os.path.join(base_dir, ".venv", "Lib", "site-packages", "PyQt5", "Qt5", "plugins")
if os.path.isdir(qt_plugins_dir):
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", qt_plugins_dir)
    os.environ.setdefault("QT_PLUGIN_PATH", qt_plugins_dir)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QTextEdit, QPushButton, QProgressBar,
    QGroupBox, QSplitter, QFileDialog, QMessageBox, QSpinBox,
    QLineEdit, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette

# ──────────────────────────────────────────────────────────────
# Signal bridge: dùng để gửi log/progress từ worker thread → UI
# ──────────────────────────────────────────────────────────────
class WorkerSignals(QObject):
    """Qt signals để giao tiếp an toàn giữa worker thread và UI thread."""
    log_message = pyqtSignal(str)           # Gửi dòng log mới
    progress_update = pyqtSignal(int)       # Cập nhật % progress bar
    stage_update = pyqtSignal(str)          # Cập nhật giai đoạn hiện tại
    fooocus_api_button_update = pyqtSignal(bool, str)
    finished = pyqtSignal(str)              # Hoàn thành, trả về đường dẫn file output
    error = pyqtSignal(str)                 # Lỗi xảy ra


class MainWindow(QMainWindow):
    """Cửa sổ chính của AIVideoCreator."""

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._connect_signals()
        self._init_ui()
        self._load_ollama_models()
        self.tts_mode_combo.currentIndexChanged.connect(self._load_voices)

    # ──────────────────────────────────────
    # Kết nối signal → slot
    # ──────────────────────────────────────
    def _connect_signals(self):
        self.signals.log_message.connect(self._append_log)
        self.signals.progress_update.connect(self._update_progress)
        self.signals.stage_update.connect(self._update_stage)
        self.signals.fooocus_api_button_update.connect(self._update_fooocus_api_button)
        self.signals.finished.connect(self._on_finished)
        self.signals.error.connect(self._on_error)

    # ──────────────────────────────────────
    # Xây dựng giao diện
    # ──────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle("🎬 AI Video Creator")
        self.setMinimumSize(900, 700)
        self.setStyleSheet(self._get_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # ── Header ──
        header = QLabel("🎬 AI Video Creator")
        header.setObjectName("header")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # ── Splitter: trái (settings + input) | phải (log) ──
        splitter = QSplitter(Qt.Horizontal)

        # === Panel trái ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)

        # ── Cài đặt mô hình ──
        settings_group = QGroupBox("⚙️ Cài đặt")
        settings_layout = QVBoxLayout()

        # Model selector
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Mô hình Ollama:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(250)
        self.model_combo.setPlaceholderText("Đang tải danh sách mô hình...")
        model_row.addWidget(self.model_combo)
        self.btn_refresh_models = QPushButton("🔄")
        self.btn_refresh_models.setFixedWidth(40)
        self.btn_refresh_models.setToolTip("Tải lại danh sách mô hình")
        self.btn_refresh_models.clicked.connect(self._load_ollama_models)
        model_row.addWidget(self.btn_refresh_models)
        settings_layout.addLayout(model_row)

        # Slide count
        slide_row = QHBoxLayout()
        slide_row.addWidget(QLabel("Số cảnh tối đa:"))
        self.slide_spinbox = QSpinBox()
        self.slide_spinbox.setRange(1, 20)
        self.slide_spinbox.setValue(5)
        slide_row.addWidget(self.slide_spinbox)
        slide_row.addStretch()
        settings_layout.addLayout(slide_row)

        # ── Resolution selector ──
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("📐 Độ phân giải:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("TikTok / Reels / Shorts dọc 9:16 (1080×1920)", (1080, 1920))
        self.resolution_combo.addItem("YouTube Full HD ngang 16:9 (1920×1080)", (1920, 1080))
        self.resolution_combo.addItem("YouTube HD ngang 16:9 (1280×720)", (1280, 720))
        self.resolution_combo.addItem("YouTube Shorts dọc 9:16 (1080×1920)", (1080, 1920))
        self.resolution_combo.addItem("Facebook Feed vuông 1:1 (1080×1080)", (1080, 1080))
        self.resolution_combo.addItem("Facebook Feed dọc 4:5 (1080×1350)", (1080, 1350))
        self.resolution_combo.addItem("Facebook Story/Reels 9:16 (1080×1920)", (1080, 1920))
        self.resolution_combo.addItem("2K QHD ngang 16:9 (2560×1440)", (2560, 1440))
        self.resolution_combo.addItem("4K UHD ngang 16:9 (3840×2160)", (3840, 2160))
        self.resolution_combo.setCurrentIndex(0)
        res_row.addWidget(self.resolution_combo)
        res_row.addStretch()
        settings_layout.addLayout(res_row)

        # ── TTS mode selector ──
        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Phong cách ảnh/video:"))
        self.style_combo = QComboBox()
        self.style_combo.addItem("Công nghệ hiện đại", "modern")
        self.style_combo.addItem("Bản tin", "news")
        self.style_combo.addItem("Giáo dục", "education")
        self.style_combo.addItem("Doanh nghiệp", "corporate")
        self.style_combo.addItem("Tối giản biên tập", "minimal")
        self.style_combo.addItem("Huyền ảo", "fantasy")
        self.style_combo.addItem("Khoa học", "science")
        self.style_combo.addItem("Ma mị", "eerie")
        self.style_combo.addItem("Điện ảnh", "cinematic")
        self.style_combo.addItem("Anime", "anime")
        self.style_combo.addItem("Thiên nhiên", "nature")
        self.style_combo.addItem("Lịch sử", "history")
        self.style_combo.setCurrentIndex(0)
        style_row.addWidget(self.style_combo)
        style_row.addStretch()
        settings_layout.addLayout(style_row)

        fooocus_row = QHBoxLayout()
        self.fooocus_checkbox = QCheckBox("Dùng Fooocus tạo ảnh minh họa + subtitle")
        self.fooocus_checkbox.setToolTip("Bật nhánh tạo video chỉ gồm ảnh Fooocus, subtitle rõ nét và audio")
        fooocus_row.addWidget(self.fooocus_checkbox)
        settings_layout.addLayout(fooocus_row)

        fooocus_endpoint_row = QHBoxLayout()
        fooocus_endpoint_row.addWidget(QLabel("Fooocus API:"))
        self.fooocus_url_input = QLineEdit("http://127.0.0.1:8888")
        self.fooocus_url_input.setToolTip("Endpoint Fooocus/Fooocus-API đang chạy. Mặc định dùng /v1/generation/text-to-image")
        fooocus_endpoint_row.addWidget(self.fooocus_url_input)
        settings_layout.addLayout(fooocus_endpoint_row)

        fooocus_dir_row = QHBoxLayout()
        fooocus_dir_row.addWidget(QLabel("Thư mục API:"))
        self.fooocus_dir_input = QLineEdit()
        default_fooocus_dir = os.path.join(base_dir, "engines", "Fooocus-API")
        if os.path.isdir(default_fooocus_dir):
            self.fooocus_dir_input.setText(default_fooocus_dir)
        else:
            self.fooocus_dir_input.setPlaceholderText("Chọn thư mục Fooocus-API hoặc Fooocus local")
        fooocus_dir_row.addWidget(self.fooocus_dir_input)
        btn_fooocus_dir = QPushButton("📁")
        btn_fooocus_dir.setFixedWidth(42)
        btn_fooocus_dir.setToolTip("Chọn thư mục chứa server Fooocus API")
        btn_fooocus_dir.clicked.connect(self._browse_fooocus_dir)
        fooocus_dir_row.addWidget(btn_fooocus_dir)
        settings_layout.addLayout(fooocus_dir_row)

        fooocus_cmd_row = QHBoxLayout()
        fooocus_cmd_row.addWidget(QLabel("Lệnh API:"))
        self.fooocus_cmd_input = QLineEdit("start_fooocus_api.bat")
        self.fooocus_cmd_input.setToolTip("Lệnh chạy trong thư mục API. Có thể sửa theo repo Fooocus/Fooocus-API của bạn")
        fooocus_cmd_row.addWidget(self.fooocus_cmd_input)
        self.btn_start_fooocus_api = QPushButton("▶ API")
        self.btn_start_fooocus_api.setFixedWidth(70)
        self.btn_start_fooocus_api.setToolTip("Khởi động Fooocus API và chờ endpoint sẵn sàng")
        self.btn_start_fooocus_api.clicked.connect(self._start_fooocus_api)
        fooocus_cmd_row.addWidget(self.btn_start_fooocus_api)
        settings_layout.addLayout(fooocus_cmd_row)

        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Ngôn ngữ video:"))
        self.language_combo = QComboBox()
        self.language_combo.addItem("Tiếng Việt", "vi")
        self.language_combo.addItem("Tiếng Anh", "en")
        self.language_combo.setCurrentIndex(0)
        language_row.addWidget(self.language_combo)
        language_row.addStretch()
        settings_layout.addLayout(language_row)

        tts_row = QHBoxLayout()
        tts_row.addWidget(QLabel("🔊 Chế độ TTS:"))
        self.tts_mode_combo = QComboBox()
        self.tts_mode_combo.addItem("🎯 Chuẩn (chất lượng cao)", "standard")
        self.tts_mode_combo.addItem("⚡ Nhanh (CPU)", "turbo")
        self.tts_mode_combo.setCurrentIndex(0)
        tts_row.addWidget(self.tts_mode_combo)
        self.btn_test_tts = QPushButton("Thử TTS")
        self.btn_test_tts.setFixedWidth(90)
        self.btn_test_tts.setToolTip("Tạo thử một file audio ngắn trước khi chạy pipeline")
        self.btn_test_tts.clicked.connect(self._test_tts)
        tts_row.addWidget(self.btn_test_tts)
        tts_row.addStretch()
        settings_layout.addLayout(tts_row)

        # ── Voice selector ──
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("🎤 Giọng nói:"))
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(250)
        self.voice_combo.addItem("(Giọng mặc định)", None)
        voice_row.addWidget(self.voice_combo)
        self.btn_refresh_voices = QPushButton("🔄")
        self.btn_refresh_voices.setFixedWidth(40)
        self.btn_refresh_voices.setToolTip("Tải danh sách giọng nói từ VieNeu")
        self.btn_refresh_voices.clicked.connect(self._load_voices)
        voice_row.addWidget(self.btn_refresh_voices)
        settings_layout.addLayout(voice_row)

        # ── Background music ──
        music_row = QHBoxLayout()
        music_row.addWidget(QLabel("🎵 Nhạc nền:"))
        self.music_path_input = QLineEdit()
        self.music_path_input.setPlaceholderText("Không có (tùy chọn)")
        self.music_path_input.setReadOnly(True)
        music_row.addWidget(self.music_path_input)
        btn_music = QPushButton("📁 Chọn")
        btn_music.setFixedWidth(80)
        btn_music.clicked.connect(self._browse_music)
        music_row.addWidget(btn_music)
        btn_clear_music = QPushButton("❌")
        btn_clear_music.setFixedWidth(40)
        btn_clear_music.setToolTip("Xóa nhạc nền")
        btn_clear_music.clicked.connect(lambda: self.music_path_input.clear())
        music_row.addWidget(btn_clear_music)
        settings_layout.addLayout(music_row)

        # ── Music volume ──
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("🔉 Volume nhạc nền:"))
        self.music_volume_spin = QSpinBox()
        self.music_volume_spin.setRange(5, 100)
        self.music_volume_spin.setValue(20)
        self.music_volume_spin.setSuffix("%")
        self.music_volume_spin.setToolTip("Âm lượng nhạc nền so với giọng nói (% thấp = nhạc nhỏ)")
        vol_row.addWidget(self.music_volume_spin)
        vol_row.addStretch()
        settings_layout.addLayout(vol_row)

        # Output folder
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Thư mục xuất:"))
        self.output_label = QLabel(os.path.join(os.getcwd(), "output"))
        self.output_label.setStyleSheet("color: #aaa; font-size: 11px;")
        output_row.addWidget(self.output_label)
        btn_browse = QPushButton("📁 Chọn")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_output)
        output_row.addWidget(btn_browse)
        settings_layout.addLayout(output_row)

        self.resume_checkbox = QCheckBox("Tiếp tục từ bước lỗi nếu có file tạm")
        self.resume_checkbox.setToolTip("Dùng lại plan, HTML, video và audio đã tạo trong temp_* để không phải chạy lại từ đầu")
        settings_layout.addWidget(self.resume_checkbox)

        settings_group.setLayout(settings_layout)
        left_layout.addWidget(settings_group)

        # ── Nhập prompt ──
        input_group = QGroupBox("💡 Ý tưởng Video")
        input_layout = QVBoxLayout()
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "Nhập ý tưởng video của bạn ở đây...\n\n"
            "Ví dụ: Tạo video giới thiệu về lịch sử Việt Nam qua 5 giai đoạn, "
            "mỗi cảnh có hình nền đẹp và chữ trình bày rõ ràng."
        )
        self.prompt_input.setMinimumHeight(150)
        input_layout.addWidget(self.prompt_input)
        input_group.setLayout(input_layout)
        left_layout.addWidget(input_group)

        # ── Nút bắt đầu ──
        self.btn_start = QPushButton("🚀 Bắt đầu tạo Video")
        self.btn_start.setObjectName("startButton")
        self.btn_start.setMinimumHeight(50)
        self.btn_start.clicked.connect(self._start_generation)
        left_layout.addWidget(self.btn_start)

        # ── Giai đoạn hiện tại ──
        self.stage_label = QLabel("⏳ Sẵn sàng")
        self.stage_label.setObjectName("stageLabel")
        self.stage_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.stage_label)

        # ── Progress bar ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        left_layout.addWidget(self.progress_bar)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # === Panel phải: Log ===
        log_group = QGroupBox("📋 Nhật ký tiến trình")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_output)

        # Nút xóa log
        btn_clear_log = QPushButton("🗑️ Xóa log")
        btn_clear_log.clicked.connect(self.log_output.clear)
        log_layout.addWidget(btn_clear_log)

        log_group.setLayout(log_layout)
        splitter.addWidget(log_group)

        splitter.setSizes([450, 450])
        main_layout.addWidget(splitter)

    # ──────────────────────────────────────
    # Stylesheet
    # ──────────────────────────────────────
    def _get_stylesheet(self):
        return """
        QMainWindow {
            background-color: #1a1a2e;
        }
        QWidget {
            color: #e0e0e0;
            font-family: 'Segoe UI', sans-serif;
            font-size: 13px;
        }
        #header {
            font-size: 28px;
            font-weight: bold;
            color: #00d4ff;
            padding: 10px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #0f3460, stop:1 #16213e);
            border-radius: 10px;
            margin-bottom: 5px;
        }
        QGroupBox {
            border: 1px solid #333;
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 15px;
            background-color: #16213e;
        }
        QGroupBox::title {
            color: #00d4ff;
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QComboBox, QSpinBox, QLineEdit {
            background-color: #0f3460;
            border: 1px solid #444;
            border-radius: 5px;
            padding: 6px 10px;
            color: #fff;
        }
        QComboBox::drop-down {
            border: none;
            width: 30px;
        }
        QComboBox QAbstractItemView {
            background-color: #0f3460;
            color: #fff;
            selection-background-color: #00d4ff;
        }
        QLineEdit[readOnly="true"] {
            color: #aaa;
        }
        QTextEdit {
            background-color: #0f3460;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 8px;
            color: #ddd;
        }
        QPushButton {
            background-color: #0f3460;
            border: 1px solid #444;
            border-radius: 6px;
            padding: 8px 16px;
            color: #e0e0e0;
        }
        QPushButton:hover {
            background-color: #1a4a7a;
            border-color: #00d4ff;
        }
        QPushButton:pressed {
            background-color: #00d4ff;
            color: #000;
        }
        #startButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #e94560, stop:1 #ff6b6b);
            color: #fff;
            font-size: 16px;
            font-weight: bold;
            border: none;
            border-radius: 10px;
        }
        #startButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ff6b6b, stop:1 #e94560);
        }
        #startButton:disabled {
            background-color: #555;
            color: #888;
        }
        #stageLabel {
            font-size: 14px;
            font-weight: bold;
            color: #ffd700;
            padding: 4px;
        }
        QProgressBar {
            border: 1px solid #333;
            border-radius: 6px;
            text-align: center;
            background-color: #0f3460;
            color: #fff;
            height: 22px;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #00d4ff, stop:1 #0f3460);
            border-radius: 5px;
        }
        QSplitter::handle {
            background-color: #333;
            width: 3px;
        }
        """

    # ──────────────────────────────────────
    # Load mô hình Ollama
    # ──────────────────────────────────────
    def _load_ollama_models(self):
        """Gọi API Ollama cục bộ để lấy danh sách model."""
        self.model_combo.clear()
        try:
            import ollama
            response = ollama.list()
            models = response.get("models", [])
            if not models:
                self.model_combo.addItem("(Không tìm thấy mô hình)")
                self._append_log("⚠️ Không tìm thấy mô hình Ollama. Hãy pull model trước.")
                return
            for m in models:
                name = m.get("name", m.get("model", "unknown"))
                size_gb = m.get("size", 0) / (1024**3)
                display = f"{name} ({size_gb:.1f} GB)" if size_gb > 0 else name
                self.model_combo.addItem(display, name)
            self._append_log(f"✅ Đã tải {len(models)} mô hình Ollama.")
        except Exception as e:
            self.model_combo.addItem("(Lỗi kết nối Ollama)")
            self._append_log(f"❌ Lỗi kết nối Ollama: {e}")
            self._append_log("💡 Hãy đảm bảo Ollama đang chạy (ollama serve).")

    # ──────────────────────────────────────
    # Duyệt thư mục output
    # ──────────────────────────────────────
    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất video")
        if folder:
            self.output_label.setText(folder)

    def _browse_music(self):
        """Chọn file nhạc nền."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file nhạc nền",
            "", "Audio Files (*.mp3 *.wav *.ogg *.m4a *.flac);;All Files (*)"
        )
        if file_path:
            self.music_path_input.setText(file_path)
            self._append_log(f"🎵 Đã chọn nhạc nền: {os.path.basename(file_path)}")

    def _browse_fooocus_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục Fooocus/Fooocus-API")
        if folder:
            self.fooocus_dir_input.setText(folder)
            self._append_log(f"🖼️ Đã chọn thư mục Fooocus API: {folder}")

    def _start_fooocus_api(self):
        """Khởi động Fooocus API trong console riêng và chờ endpoint sẵn sàng."""
        api_dir = self.fooocus_dir_input.text().strip()
        api_url = self.fooocus_url_input.text().strip() or "http://127.0.0.1:8888"
        command = self.fooocus_cmd_input.text().strip()

        if not api_dir or not os.path.isdir(api_dir):
            QMessageBox.warning(
                self,
                "Thiếu thư mục Fooocus API",
                "Vui lòng chọn thư mục chứa Fooocus-API/Fooocus trước khi khởi động API."
            )
            return
        if not command:
            QMessageBox.warning(self, "Thiếu lệnh chạy", "Vui lòng nhập lệnh khởi động Fooocus API.")
            return

        command = self._normalize_fooocus_command(api_dir, command)
        self.fooocus_cmd_input.setText(command)

        self.btn_start_fooocus_api.setEnabled(False)
        self.btn_start_fooocus_api.setText("⏳ API")
        self._append_log(f"🖼️ Khởi động Fooocus API tại: {api_dir}")
        self._append_log(f"▶ {command}")

        def worker():
            try:
                if self._is_fooocus_api_ready(api_url):
                    self.signals.log_message.emit(f"✅ Fooocus API đang chạy sẵn: {api_url}")
                    self.signals.stage_update.emit("✅ Fooocus API sẵn sàng")
                    return

                self._launch_fooocus_api_process(api_dir, command)

                if self._wait_for_fooocus_api(api_url, timeout_sec=900):
                    self.signals.log_message.emit(f"✅ Fooocus API đã sẵn sàng: {api_url}")
                    self.signals.stage_update.emit("✅ Fooocus API sẵn sàng")
                else:
                    self.signals.log_message.emit(
                        f"⚠️ Đã mở tiến trình API nhưng chưa kết nối được {api_url}. "
                        "Hãy xem cửa sổ Fooocus API để kiểm tra lỗi hoặc chỉnh lại endpoint/lệnh chạy."
                    )
                    self.signals.stage_update.emit("⚠️ Chưa kết nối được Fooocus API")
            except Exception as e:
                self.signals.log_message.emit(f"❌ Không khởi động được Fooocus API: {e}")
                self.signals.stage_update.emit("❌ Lỗi khởi động Fooocus API")
            finally:
                self.signals.fooocus_api_button_update.emit(True, "▶ API")

        threading.Thread(target=worker, daemon=True).start()

    def _normalize_fooocus_command(self, api_dir: str, command: str) -> str:
        command = (command or "").strip() or "start_fooocus_api.bat"
        bundled_launcher = os.path.join(api_dir, "start_fooocus_api.bat")
        if os.path.exists(bundled_launcher):
            command_lower = command.lower()
            if (
                command_lower.startswith("python ")
                or command_lower.startswith("py ")
                or " main.py" in command_lower
                or command_lower == "main.py"
            ):
                return "start_fooocus_api.bat"
        return command

    def _launch_fooocus_api_process(self, api_dir: str, command: str):
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")

        if os.name == "nt":
            subprocess.Popen(
                ["cmd", "/k", command],
                cwd=api_dir,
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen(command, cwd=api_dir, env=env, shell=True)

    def _is_fooocus_api_ready(self, api_url: str) -> bool:
        import requests

        try:
            response = requests.get(api_url, timeout=3)
            return response.status_code < 500
        except Exception:
            return False

    def _ensure_fooocus_api_ready(self, api_url: str, api_dir: str, command: str):
        if self._is_fooocus_api_ready(api_url):
            self.signals.log_message.emit(f"✅ Fooocus API đang chạy sẵn: {api_url}")
            return

        if not api_dir or not os.path.isdir(api_dir):
            raise RuntimeError(
                "Fooocus API chưa chạy và chưa có thư mục API hợp lệ. "
                "Hãy chọn thư mục engines\\Fooocus-API hoặc bấm nút API trước."
            )

        command = self._normalize_fooocus_command(api_dir, command)
        self.signals.log_message.emit("ℹ️ Fooocus API chưa chạy, app sẽ tự khởi động engine nội bộ.")
        self.signals.log_message.emit(f"🖼️ Thư mục API: {api_dir}")
        self.signals.log_message.emit(f"▶ {command}")
        self._launch_fooocus_api_process(api_dir, command)

        if not self._wait_for_fooocus_api(api_url, timeout_sec=900):
            raise RuntimeError(
                f"Đã mở Fooocus API nhưng chưa kết nối được {api_url}. "
                "Hãy xem cửa sổ Fooocus API để kiểm tra cài dependency/model hoặc lỗi CUDA/Torch."
            )
        self.signals.log_message.emit(f"✅ Fooocus API đã sẵn sàng: {api_url}")

    def _wait_for_fooocus_api(self, api_url: str, timeout_sec: int = 90) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self._is_fooocus_api_ready(api_url):
                return True
            time.sleep(2)
        return False

    def _load_voices(self):
        """Tải danh sách giọng nói từ VieNeu-TTS."""
        self.voice_combo.clear()
        self.voice_combo.addItem("(Giọng mặc định)", None)
        self._append_log("🔄 Đang tải danh sách giọng nói...")
        try:
            from vieneu import Vieneu
            tts_mode = self.tts_mode_combo.currentData() or "standard"
            if tts_mode == "turbo":
                tts = Vieneu(mode="turbo")
            else:
                tts = Vieneu(mode="standard")
            voices = tts.list_preset_voices()
            for desc, voice_id in voices:
                self.voice_combo.addItem(f"{desc}", voice_id)
            self._append_log(f"✅ Đã tải {len(voices)} giọng nói")
        except Exception as e:
            self._append_log(f"⚠️ Không thể tải giọng nói: {e}")
            self._append_log("💡 Sẽ sử dụng giọng mặc định khi tạo video")

    def _test_tts(self):
        """Tạo thử một đoạn audio ngắn bằng cấu hình TTS hiện tại."""
        tts_mode = self.tts_mode_combo.currentData() or "standard"
        voice_id = self.voice_combo.currentData()
        sample_text = "Đây là đoạn kiểm tra giọng nói của AI Video Creator."

        def worker():
            try:
                from module_audio_agent import AudioAgent

                self.signals.stage_update.emit("🔊 Đang test TTS...")
                audio_agent = AudioAgent(self.signals, mode=tts_mode)
                output_path = audio_agent.test_tts_sample(sample_text, voice_id=voice_id)
                self.signals.log_message.emit(f"✅ Thử TTS hoàn tất: {output_path}")
                self.signals.stage_update.emit("✅ Thử TTS thành công")
            except Exception as e:
                self.signals.log_message.emit(f"❌ Thử TTS thất bại: {e}")
                self.signals.stage_update.emit("❌ Thử TTS lỗi")

        threading.Thread(target=worker, daemon=True).start()

    # ──────────────────────────────────────
    # Bắt đầu quá trình tạo video
    # ──────────────────────────────────────
    def _start_generation(self):
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập ý tưởng video!")
            return

        model_name = self.model_combo.currentData()
        if not model_name:
            QMessageBox.warning(self, "Thiếu mô hình", "Vui lòng chọn mô hình Ollama!")
            return

        # Disable nút và reset
        self.btn_start.setEnabled(False)
        self.btn_start.setText("⏳ Đang xử lý...")
        self.progress_bar.setValue(0)
        self.log_output.clear()

        max_slides = self.slide_spinbox.value()
        output_dir = self.output_label.text()
        os.makedirs(output_dir, exist_ok=True)

        # Thu thập các tùy chọn mới
        resolution = self.resolution_combo.currentData() or (1280, 720)
        style_preset = self.style_combo.currentData() or "modern"
        output_language = self.language_combo.currentData() or "vi"
        tts_mode = self.tts_mode_combo.currentData() or "standard"
        voice_id = self.voice_combo.currentData()  # None = giọng mặc định
        music_path = self.music_path_input.text().strip() or None
        music_volume = self.music_volume_spin.value() / 100.0  # 0.0 - 1.0
        resume_enabled = self.resume_checkbox.isChecked()
        fooocus_enabled = self.fooocus_checkbox.isChecked()
        fooocus_url = self.fooocus_url_input.text().strip() or "http://127.0.0.1:8888"
        fooocus_dir = self.fooocus_dir_input.text().strip()
        fooocus_command = self.fooocus_cmd_input.text().strip()

        # Chạy pipeline trong thread riêng
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(prompt, model_name, max_slides, output_dir,
                  resolution, style_preset, output_language, tts_mode, voice_id, music_path, music_volume,
                  resume_enabled, fooocus_enabled, fooocus_url, fooocus_dir, fooocus_command),
            daemon=True
        )
        thread.start()

    def _run_pipeline(self, prompt, model_name, max_slides, output_dir,
                      resolution, style_preset, output_language, tts_mode, voice_id, music_path, music_volume,
                      resume_enabled=False, fooocus_enabled=False, fooocus_url="http://127.0.0.1:8888",
                      fooocus_dir="", fooocus_command="start_fooocus_api.bat"):
        """Pipeline chính chạy trong background thread."""
        try:
            from module_video_agent import VideoAgent, VideoPlan
            from module_audio_agent import AudioAgent
            from video_assembler import VideoAssembler

            width, height = resolution
            render_mode = "Fooocus image story" if fooocus_enabled else "HTML static slides"
            self.signals.log_message.emit(f"⚙️ Cấu hình: {width}x{height}, Chế độ={render_mode}, Phong cách={style_preset}, Ngôn ngữ={output_language}, TTS={tts_mode}, Nhạc={'Có' if music_path else 'Không'}")
            if resume_enabled:
                self.signals.log_message.emit("🔁 Resume đang bật: dùng lại file tạm hợp lệ nếu có.")

            # ── Giai đoạn 1: Brainstorming ──
            self.signals.stage_update.emit("🧠 Giai đoạn 1/5: Lên ý tưởng...")
            self.signals.progress_update.emit(5)

            video_agent = VideoAgent(
                model_name,
                self.signals,
                resolution=resolution,
                style_preset=style_preset,
                output_language=output_language,
            )
            plan_path = os.path.join(video_agent.TEMP_DIR, "video_plan.json")
            plan_meta_path = os.path.join(video_agent.TEMP_DIR, "video_plan_meta.json")
            plan = None
            if resume_enabled and os.path.exists(plan_path):
                try:
                    plan_meta = {}
                    if os.path.exists(plan_meta_path):
                        with open(plan_meta_path, "r", encoding="utf-8") as f:
                            plan_meta = json.load(f)
                    if plan_meta.get("output_language") != output_language:
                        raise ValueError("Ngôn ngữ của plan cũ không khớp cấu hình hiện tại")
                    with open(plan_path, "r", encoding="utf-8") as f:
                        plan = VideoPlan.model_validate_json(f.read())
                    self.signals.log_message.emit(f"✅ Đã tải lại kế hoạch cũ: {plan_path}")
                except Exception as e:
                    self.signals.log_message.emit(f"⚠️ Không đọc được plan cũ, sẽ brainstorm lại: {e}")

            if plan is None:
                plan = video_agent.brainstorm(prompt, max_slides)
                os.makedirs(video_agent.TEMP_DIR, exist_ok=True)
                with open(plan_path, "w", encoding="utf-8") as f:
                    f.write(plan.model_dump_json(indent=2))
                with open(plan_meta_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "output_language": output_language,
                            "style_preset": style_preset,
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
                self.signals.log_message.emit(f"💾 Đã lưu kế hoạch để resume: {plan_path}")
            self.signals.progress_update.emit(15)

            # Kiểm tra TTS trước khi tốn thời gian render.
            self.signals.stage_update.emit("🔊 Kiểm tra TTS trước khi render...")
            audio_agent = AudioAgent(self.signals, mode=tts_mode)
            sample_text = plan.slides[0].narration if plan.slides else "Kiểm tra giọng nói."
            try:
                audio_agent.test_tts_sample(sample_text[:220], voice_id=voice_id)
            except Exception as e:
                raise RuntimeError(
                    f"Thử TTS thất bại với chế độ '{tts_mode}'. "
                    "Hãy thử đổi sang Turbo hoặc kiểm tra VieNeu/llama-cpp trước khi render video.\n"
                    f"Chi tiết: {e}"
                ) from e
            self.signals.progress_update.emit(25)

            if fooocus_enabled:
                from module_fooocus_agent import FooocusAgent
                from module_subtitle_agent import SubtitleAgent

                self.signals.stage_update.emit("🖼️ Kiểm tra / khởi động Fooocus API...")
                self._ensure_fooocus_api_ready(fooocus_url, fooocus_dir, fooocus_command)

                self.signals.stage_update.emit("🎨 Giai đoạn 2/5: Tạo ảnh minh họa bằng Fooocus...")
                fooocus_agent = FooocusAgent(
                    fooocus_url,
                    self.signals,
                    resolution=resolution,
                    style_preset=style_preset,
                )
                image_files = fooocus_agent.generate_images_for_plan(plan, resume=resume_enabled)
                self.signals.progress_update.emit(50)

                self.signals.stage_update.emit("🔊 Giai đoạn 3/5: Tạo giọng nói TTS...")
                audio_agent = AudioAgent(self.signals, mode=tts_mode)
                narrations = [slide.narration for slide in plan.slides]
                audio_files = audio_agent.generate_audio(narrations, voice_id=voice_id, resume=resume_enabled)
                self.signals.progress_update.emit(75)

                self.signals.stage_update.emit("💬 Giai đoạn 4/5: Tạo subtitle theo đúng frame...")
                subtitle_agent = SubtitleAgent(
                    model_name,
                    self.signals,
                    fps=30,
                    output_language=output_language,
                    resolution=resolution,
                )
                subtitle_cues = subtitle_agent.generate_for_plan(plan, audio_files, resume=resume_enabled)
                self.signals.progress_update.emit(85)

                self.signals.stage_update.emit("🎬 Giai đoạn 5/5: Dựng video ảnh + subtitle + audio...")
                assembler = VideoAssembler(self.signals)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(output_dir, f"fooocus_video_{timestamp}.mp4")
                assembler.assemble_image_story(
                    image_files,
                    audio_files,
                    subtitle_cues,
                    output_path,
                    resolution=resolution,
                    bg_music_path=music_path,
                    bg_music_volume=music_volume,
                )
                self.signals.progress_update.emit(100)
                self.signals.finished.emit(output_path)
                return

            # ── Giai đoạn 2: Viết HTML/CSS ──
            self.signals.stage_update.emit("💻 Giai đoạn 2/5: Viết HTML/CSS cho các cảnh...")
            html_files = video_agent.generate_html_slides(plan, resume=resume_enabled)
            self.signals.progress_update.emit(35)
            self.signals.stage_update.emit("🖼️ Xuất ảnh xem trước PNG cho các cảnh...")
            preview_files = video_agent.render_preview_images(html_files, resume=resume_enabled)
            self.signals.log_message.emit(
                f"🖼️ Preview PNG đã sẵn sàng: {os.path.abspath(video_agent.PREVIEW_DIR)} ({len(preview_files)} file)"
            )
            self.signals.progress_update.emit(42)

            # ── Giai đoạn 3: Render cảnh → video ──
            self.signals.stage_update.emit("🎥 Giai đoạn 3/5: Render các cảnh thành video...")
            durations = [slide.duration_seconds for slide in plan.slides]
            video_clips = video_agent.render_slides_to_video(html_files, durations=durations, resume=resume_enabled)
            self.signals.progress_update.emit(55)

            # ── Giai đoạn 4: TTS Audio ──
            self.signals.stage_update.emit("🔊 Giai đoạn 4/5: Tạo giọng nói TTS...")
            audio_agent = AudioAgent(self.signals, mode=tts_mode)
            narrations = [slide.narration for slide in plan.slides]
            audio_files = audio_agent.generate_audio(narrations, voice_id=voice_id, resume=resume_enabled)
            self.signals.progress_update.emit(75)

            # ── Giai đoạn 5: Merging ──
            self.signals.stage_update.emit("🔧 Giai đoạn 5/5: Ghép video + âm thanh...")
            assembler = VideoAssembler(self.signals)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"video_{timestamp}.mp4")
            assembler.assemble(
                video_clips, audio_files, output_path,
                bg_music_path=music_path,
                bg_music_volume=music_volume
            )
            self.signals.progress_update.emit(100)

            self.signals.finished.emit(output_path)

        except Exception as e:
            import traceback
            self.signals.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")

    # ──────────────────────────────────────
    # Slots (nhận signal từ worker thread)
    # ──────────────────────────────────────
    def _append_log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{timestamp}] {msg}")
        # Auto-scroll xuống
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_progress(self, value: int):
        self.progress_bar.setValue(value)

    def _update_stage(self, stage: str):
        self.stage_label.setText(stage)
        self._append_log(f"━━━ {stage} ━━━")

    def _update_fooocus_api_button(self, enabled: bool, text: str):
        self.btn_start_fooocus_api.setEnabled(enabled)
        self.btn_start_fooocus_api.setText(text)

    def _on_finished(self, output_path: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("🚀 Bắt đầu tạo Video")
        self.stage_label.setText("✅ Hoàn thành!")
        self._append_log(f"🎉 Video đã tạo xong: {output_path}")
        QMessageBox.information(
            self, "Thành công!",
            f"Video đã được tạo thành công!\n\n📁 {output_path}"
        )

    def _on_error(self, error_msg: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("🚀 Bắt đầu tạo Video")
        self.stage_label.setText("❌ Lỗi!")
        self._append_log(f"❌ LỖI: {error_msg}")
        QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi:\n\n{error_msg[:500]}")


# ══════════════════════════════════════
# Entry point
# ══════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette bổ sung
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(26, 26, 46))
    palette.setColor(QPalette.WindowText, QColor(224, 224, 224))
    palette.setColor(QPalette.Base, QColor(15, 52, 96))
    palette.setColor(QPalette.AlternateBase, QColor(22, 33, 62))
    palette.setColor(QPalette.ToolTipBase, QColor(0, 0, 0))
    palette.setColor(QPalette.ToolTipText, QColor(224, 224, 224))
    palette.setColor(QPalette.Text, QColor(224, 224, 224))
    palette.setColor(QPalette.Button, QColor(15, 52, 96))
    palette.setColor(QPalette.ButtonText, QColor(224, 224, 224))
    palette.setColor(QPalette.Highlight, QColor(0, 212, 255))
    palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
