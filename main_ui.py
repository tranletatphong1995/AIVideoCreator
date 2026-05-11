"""
AIVideoCreator - Main UI
Giao diá»‡n chÃ­nh sá»­ dá»¥ng PyQt5 Ä‘á»ƒ táº¡o video AI tá»± Ä‘á»™ng.
Pipeline: Brainstorming â†’ Coding HTML â†’ Rendering â†’ Audio TTS â†’ Merging
"""

import sys
import os
import threading
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Signal bridge: dÃ¹ng Ä‘á»ƒ gá»­i log/progress tá»« worker thread â†’ UI
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class WorkerSignals(QObject):
    """Qt signals Ä‘á»ƒ giao tiáº¿p an toÃ n giá»¯a worker thread vÃ  UI thread."""
    log_message = pyqtSignal(str)           # Gá»­i dÃ²ng log má»›i
    progress_update = pyqtSignal(int)       # Cáº­p nháº­t % progress bar
    stage_update = pyqtSignal(str)          # Cáº­p nháº­t giai Ä‘oáº¡n hiá»‡n táº¡i
    fooocus_api_button_update = pyqtSignal(bool, str)
    ima2_button_update = pyqtSignal(bool, str)
    finished = pyqtSignal(str)              # HoÃ n thÃ nh, tráº£ vá» Ä‘Æ°á»ng dáº«n file output
    error = pyqtSignal(str)                 # Lá»—i xáº£y ra


class MainWindow(QMainWindow):
    """Cá»­a sá»• chÃ­nh cá»§a AIVideoCreator."""

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._connect_signals()
        self._init_ui()
        self._load_ollama_models()
        self.tts_mode_combo.currentIndexChanged.connect(self._load_voices)
        self.ai_mode_combo.currentIndexChanged.connect(self._update_ai_mode_controls)
        self._update_ai_mode_controls()

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Káº¿t ná»‘i signal â†’ slot
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _connect_signals(self):
        self.signals.log_message.connect(self._append_log)
        self.signals.progress_update.connect(self._update_progress)
        self.signals.stage_update.connect(self._update_stage)
        self.signals.fooocus_api_button_update.connect(self._update_fooocus_api_button)
        self.signals.ima2_button_update.connect(self._update_ima2_button)
        self.signals.finished.connect(self._on_finished)
        self.signals.error.connect(self._on_error)

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # XÃ¢y dá»±ng giao diá»‡n
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _init_ui(self):
        self.setWindowTitle("ðŸŽ¬ AI Video Creator")
        self.setMinimumSize(900, 700)
        self.setStyleSheet(self._get_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # â”€â”€ Header â”€â”€
        header = QLabel("ðŸŽ¬ AI Video Creator")
        header.setObjectName("header")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # â”€â”€ Splitter: trÃ¡i (settings + input) | pháº£i (log) â”€â”€
        splitter = QSplitter(Qt.Horizontal)

        # === Panel trÃ¡i ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)

        # â”€â”€ CÃ i Ä‘áº·t mÃ´ hÃ¬nh â”€â”€
        settings_group = QGroupBox("âš™ï¸ CÃ i Ä‘áº·t")
        settings_layout = QVBoxLayout()

        ai_mode_row = QHBoxLayout()
        self.ai_mode_label = QLabel("Che do AI:")
        ai_mode_row.addWidget(self.ai_mode_label)
        self.ai_mode_combo = QComboBox()
        self.ai_mode_combo.addItem("Local Ollama/Fooocus", "local")
        self.ai_mode_combo.addItem("Online ChatGPT/ima2-gen", "online")
        self.ai_mode_combo.setCurrentIndex(0)
        ai_mode_row.addWidget(self.ai_mode_combo)
        settings_layout.addLayout(ai_mode_row)

        online_model_row = QHBoxLayout()
        self.online_model_label = QLabel("ChatGPT model:")
        online_model_row.addWidget(self.online_model_label)
        self.online_model_combo = QComboBox()
        self.online_model_combo.addItem("gpt-5.4-mini", "gpt-5.4-mini")
        self.online_model_combo.addItem("gpt-5.4", "gpt-5.4")
        self.online_model_combo.addItem("gpt-5.5", "gpt-5.5")
        online_model_row.addWidget(self.online_model_combo)
        settings_layout.addLayout(online_model_row)

        online_parallel_row = QHBoxLayout()
        self.online_parallel_label = QLabel("ChatGPT song song:")
        online_parallel_row.addWidget(self.online_parallel_label)
        self.online_parallel_spin = QSpinBox()
        self.online_parallel_spin.setRange(1, 8)
        self.online_parallel_spin.setValue(4)
        self.online_parallel_spin.setToolTip("Sá»‘ tÃ¡c vá»¥ ChatGPT/ima2-gen cháº¡y song song. TÄƒng cao sáº½ nhanh hÆ¡n nhÆ°ng dÃ¹ng quota/máº¡ng nhiá»u hÆ¡n.")
        online_parallel_row.addWidget(self.online_parallel_spin)
        online_parallel_row.addStretch()
        settings_layout.addLayout(online_parallel_row)

        ima2_endpoint_row = QHBoxLayout()
        self.ima2_url_label = QLabel("ima2 server:")
        ima2_endpoint_row.addWidget(self.ima2_url_label)
        self.ima2_url_input = QLineEdit("http://127.0.0.1:3333")
        self.ima2_url_input.setToolTip("ima2-gen server. If port 3333 is busy, the app also reads ~/.ima2/server.json.")
        ima2_endpoint_row.addWidget(self.ima2_url_input)
        self.btn_start_ima2 = QPushButton("Start ima2")
        self.btn_start_ima2.setFixedWidth(90)
        self.btn_start_ima2.clicked.connect(self._start_ima2_server)
        ima2_endpoint_row.addWidget(self.btn_start_ima2)
        settings_layout.addLayout(ima2_endpoint_row)

        chatgpt_login_row = QHBoxLayout()
        self.btn_chatgpt_login = QPushButton("Login ChatGPT")
        self.btn_chatgpt_login.setToolTip("Run: npx --yes @openai/codex login")
        self.btn_chatgpt_login.clicked.connect(self._login_chatgpt)
        chatgpt_login_row.addWidget(self.btn_chatgpt_login)
        chatgpt_login_row.addStretch()
        settings_layout.addLayout(chatgpt_login_row)

        # Model selector
        model_row = QHBoxLayout()
        self.ollama_model_label = QLabel("MÃ´ hÃ¬nh Ollama:")
        model_row.addWidget(self.ollama_model_label)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(250)
        self.model_combo.setPlaceholderText("Äang táº£i danh sÃ¡ch mÃ´ hÃ¬nh...")
        model_row.addWidget(self.model_combo)
        self.btn_refresh_models = QPushButton("ðŸ”„")
        self.btn_refresh_models.setFixedWidth(40)
        self.btn_refresh_models.setToolTip("Táº£i láº¡i danh sÃ¡ch mÃ´ hÃ¬nh")
        self.btn_refresh_models.clicked.connect(self._load_ollama_models)
        model_row.addWidget(self.btn_refresh_models)
        settings_layout.addLayout(model_row)

        # Slide count
        slide_row = QHBoxLayout()
        slide_row.addWidget(QLabel("Sá»‘ cáº£nh tá»‘i Ä‘a:"))
        self.slide_spinbox = QSpinBox()
        self.slide_spinbox.setRange(1, 20)
        self.slide_spinbox.setValue(5)
        slide_row.addWidget(self.slide_spinbox)
        slide_row.addStretch()
        settings_layout.addLayout(slide_row)

        # â”€â”€ Resolution selector â”€â”€
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("ðŸ“ Äá»™ phÃ¢n giáº£i:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("TikTok / Reels / Shorts dá»c 9:16 (1080Ã—1920)", (1080, 1920))
        self.resolution_combo.addItem("YouTube Full HD ngang 16:9 (1920Ã—1080)", (1920, 1080))
        self.resolution_combo.addItem("YouTube HD ngang 16:9 (1280Ã—720)", (1280, 720))
        self.resolution_combo.addItem("YouTube Shorts dá»c 9:16 (1080Ã—1920)", (1080, 1920))
        self.resolution_combo.addItem("Facebook Feed vuÃ´ng 1:1 (1080Ã—1080)", (1080, 1080))
        self.resolution_combo.addItem("Facebook Feed dá»c 4:5 (1080Ã—1350)", (1080, 1350))
        self.resolution_combo.addItem("Facebook Story/Reels 9:16 (1080Ã—1920)", (1080, 1920))
        self.resolution_combo.addItem("2K QHD ngang 16:9 (2560Ã—1440)", (2560, 1440))
        self.resolution_combo.addItem("4K UHD ngang 16:9 (3840Ã—2160)", (3840, 2160))
        self.resolution_combo.setCurrentIndex(0)
        res_row.addWidget(self.resolution_combo)
        res_row.addStretch()
        settings_layout.addLayout(res_row)

        render_profile_row = QHBoxLayout()
        render_profile_row.addWidget(QLabel("Tá»‘c Ä‘á»™ render:"))
        self.render_profile_combo = QComboBox()
        self.render_profile_combo.addItem("Fast preview", "fast")
        self.render_profile_combo.addItem("Final quality", "final")
        self.render_profile_combo.setCurrentIndex(0)
        self.render_profile_combo.setToolTip("Fast dÃ¹ng subtitle fallback, preview resolution tháº¥p vÃ  encode veryfast. Final giá»¯ cháº¥t lÆ°á»£ng cao hÆ¡n.")
        render_profile_row.addWidget(self.render_profile_combo)
        render_profile_row.addStretch()
        settings_layout.addLayout(render_profile_row)

        # â”€â”€ TTS mode selector â”€â”€
        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Phong cÃ¡ch áº£nh/video:"))
        self.style_combo = QComboBox()
        self.style_combo.addItem("CÃ´ng nghá»‡ hiá»‡n Ä‘áº¡i", "modern")
        self.style_combo.addItem("Báº£n tin", "news")
        self.style_combo.addItem("GiÃ¡o dá»¥c", "education")
        self.style_combo.addItem("Doanh nghiá»‡p", "corporate")
        self.style_combo.addItem("Tá»‘i giáº£n biÃªn táº­p", "minimal")
        self.style_combo.addItem("Huyá»n áº£o", "fantasy")
        self.style_combo.addItem("Khoa há»c", "science")
        self.style_combo.addItem("Ma má»‹", "eerie")
        self.style_combo.addItem("Äiá»‡n áº£nh", "cinematic")
        self.style_combo.addItem("Anime", "anime")
        self.style_combo.addItem("ThiÃªn nhiÃªn", "nature")
        self.style_combo.addItem("Lá»‹ch sá»­", "history")
        self.style_combo.setCurrentIndex(0)
        style_row.addWidget(self.style_combo)
        style_row.addStretch()
        settings_layout.addLayout(style_row)

        fooocus_row = QHBoxLayout()
        self.fooocus_checkbox = QCheckBox("DÃ¹ng Fooocus táº¡o áº£nh minh há»a + subtitle")
        self.fooocus_checkbox.setToolTip("Báº­t nhÃ¡nh táº¡o video chá»‰ gá»“m áº£nh Fooocus, subtitle rÃµ nÃ©t vÃ  audio")
        fooocus_row.addWidget(self.fooocus_checkbox)
        settings_layout.addLayout(fooocus_row)

        fooocus_endpoint_row = QHBoxLayout()
        self.fooocus_url_label = QLabel("Fooocus API:")
        fooocus_endpoint_row.addWidget(self.fooocus_url_label)
        self.fooocus_url_input = QLineEdit("http://127.0.0.1:8888")
        self.fooocus_url_input.setToolTip("Endpoint Fooocus/Fooocus-API Ä‘ang cháº¡y. Máº·c Ä‘á»‹nh dÃ¹ng /v1/generation/text-to-image")
        fooocus_endpoint_row.addWidget(self.fooocus_url_input)
        settings_layout.addLayout(fooocus_endpoint_row)

        fooocus_dir_row = QHBoxLayout()
        self.fooocus_dir_label = QLabel("ThÆ° má»¥c API:")
        fooocus_dir_row.addWidget(self.fooocus_dir_label)
        self.fooocus_dir_input = QLineEdit()
        default_fooocus_dir = os.path.join(base_dir, "engines", "Fooocus-API")
        if os.path.isdir(default_fooocus_dir):
            self.fooocus_dir_input.setText(default_fooocus_dir)
        else:
            self.fooocus_dir_input.setPlaceholderText("Chá»n thÆ° má»¥c Fooocus-API hoáº·c Fooocus local")
        fooocus_dir_row.addWidget(self.fooocus_dir_input)
        self.btn_fooocus_dir = QPushButton("ðŸ“")
        self.btn_fooocus_dir.setFixedWidth(42)
        self.btn_fooocus_dir.setToolTip("Chá»n thÆ° má»¥c chá»©a server Fooocus API")
        self.btn_fooocus_dir.clicked.connect(self._browse_fooocus_dir)
        fooocus_dir_row.addWidget(self.btn_fooocus_dir)
        settings_layout.addLayout(fooocus_dir_row)

        fooocus_cmd_row = QHBoxLayout()
        self.fooocus_cmd_label = QLabel("Lá»‡nh API:")
        fooocus_cmd_row.addWidget(self.fooocus_cmd_label)
        self.fooocus_cmd_input = QLineEdit("start_fooocus_api.bat")
        self.fooocus_cmd_input.setToolTip("Lá»‡nh cháº¡y trong thÆ° má»¥c API. CÃ³ thá»ƒ sá»­a theo repo Fooocus/Fooocus-API cá»§a báº¡n")
        fooocus_cmd_row.addWidget(self.fooocus_cmd_input)
        self.btn_start_fooocus_api = QPushButton("â–¶ API")
        self.btn_start_fooocus_api.setFixedWidth(70)
        self.btn_start_fooocus_api.setToolTip("Khá»Ÿi Ä‘á»™ng Fooocus API vÃ  chá» endpoint sáºµn sÃ ng")
        self.btn_start_fooocus_api.clicked.connect(self._start_fooocus_api)
        fooocus_cmd_row.addWidget(self.btn_start_fooocus_api)
        settings_layout.addLayout(fooocus_cmd_row)

        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("NgÃ´n ngá»¯ video:"))
        self.language_combo = QComboBox()
        self.language_combo.addItem("Tiáº¿ng Viá»‡t", "vi")
        self.language_combo.addItem("Tiáº¿ng Anh", "en")
        self.language_combo.setCurrentIndex(0)
        language_row.addWidget(self.language_combo)
        language_row.addStretch()
        settings_layout.addLayout(language_row)

        tts_row = QHBoxLayout()
        tts_row.addWidget(QLabel("ðŸ”Š Cháº¿ Ä‘á»™ TTS:"))
        self.tts_mode_combo = QComboBox()
        self.tts_mode_combo.addItem("ðŸŽ¯ Chuáº©n (cháº¥t lÆ°á»£ng cao)", "standard")
        self.tts_mode_combo.addItem("âš¡ Nhanh (CPU)", "turbo")
        self.tts_mode_combo.setCurrentIndex(0)
        tts_row.addWidget(self.tts_mode_combo)
        self.btn_test_tts = QPushButton("Thá»­ TTS")
        self.btn_test_tts.setFixedWidth(90)
        self.btn_test_tts.setToolTip("Táº¡o thá»­ má»™t file audio ngáº¯n trÆ°á»›c khi cháº¡y pipeline")
        self.btn_test_tts.clicked.connect(self._test_tts)
        tts_row.addWidget(self.btn_test_tts)
        tts_row.addStretch()
        settings_layout.addLayout(tts_row)

        # â”€â”€ Voice selector â”€â”€
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("ðŸŽ¤ Giá»ng nÃ³i:"))
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(250)
        self.voice_combo.addItem("(Giá»ng máº·c Ä‘á»‹nh)", None)
        voice_row.addWidget(self.voice_combo)
        self.btn_refresh_voices = QPushButton("ðŸ”„")
        self.btn_refresh_voices.setFixedWidth(40)
        self.btn_refresh_voices.setToolTip("Táº£i danh sÃ¡ch giá»ng nÃ³i tá»« VieNeu")
        self.btn_refresh_voices.clicked.connect(self._load_voices)
        voice_row.addWidget(self.btn_refresh_voices)
        settings_layout.addLayout(voice_row)

        # â”€â”€ Background music â”€â”€
        music_row = QHBoxLayout()
        music_row.addWidget(QLabel("ðŸŽµ Nháº¡c ná»n:"))
        self.music_path_input = QLineEdit()
        self.music_path_input.setPlaceholderText("KhÃ´ng cÃ³ (tÃ¹y chá»n)")
        self.music_path_input.setReadOnly(True)
        music_row.addWidget(self.music_path_input)
        btn_music = QPushButton("ðŸ“ Chá»n")
        btn_music.setFixedWidth(80)
        btn_music.clicked.connect(self._browse_music)
        music_row.addWidget(btn_music)
        btn_clear_music = QPushButton("âŒ")
        btn_clear_music.setFixedWidth(40)
        btn_clear_music.setToolTip("XÃ³a nháº¡c ná»n")
        btn_clear_music.clicked.connect(lambda: self.music_path_input.clear())
        music_row.addWidget(btn_clear_music)
        settings_layout.addLayout(music_row)

        # â”€â”€ Music volume â”€â”€
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("ðŸ”‰ Volume nháº¡c ná»n:"))
        self.music_volume_spin = QSpinBox()
        self.music_volume_spin.setRange(5, 100)
        self.music_volume_spin.setValue(20)
        self.music_volume_spin.setSuffix("%")
        self.music_volume_spin.setToolTip("Ã‚m lÆ°á»£ng nháº¡c ná»n so vá»›i giá»ng nÃ³i (% tháº¥p = nháº¡c nhá»)")
        vol_row.addWidget(self.music_volume_spin)
        vol_row.addStretch()
        settings_layout.addLayout(vol_row)

        # Output folder
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("ThÆ° má»¥c xuáº¥t:"))
        self.output_label = QLabel(os.path.join(os.getcwd(), "output"))
        self.output_label.setStyleSheet("color: #aaa; font-size: 11px;")
        output_row.addWidget(self.output_label)
        btn_browse = QPushButton("ðŸ“ Chá»n")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_output)
        output_row.addWidget(btn_browse)
        settings_layout.addLayout(output_row)

        self.resume_checkbox = QCheckBox("Tiáº¿p tá»¥c tá»« bÆ°á»›c lá»—i náº¿u cÃ³ file táº¡m")
        self.resume_checkbox.setToolTip("DÃ¹ng láº¡i plan, HTML, video vÃ  audio Ä‘Ã£ táº¡o trong temp_* Ä‘á»ƒ khÃ´ng pháº£i cháº¡y láº¡i tá»« Ä‘áº§u")
        settings_layout.addWidget(self.resume_checkbox)

        settings_group.setLayout(settings_layout)
        left_layout.addWidget(settings_group)

        # â”€â”€ Nháº­p prompt â”€â”€
        input_group = QGroupBox("ðŸ’¡ Ã tÆ°á»Ÿng Video")
        input_layout = QVBoxLayout()
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "Nháº­p Ã½ tÆ°á»Ÿng video cá»§a báº¡n á»Ÿ Ä‘Ã¢y...\n\n"
            "VÃ­ dá»¥: Táº¡o video giá»›i thiá»‡u vá» lá»‹ch sá»­ Viá»‡t Nam qua 5 giai Ä‘oáº¡n, "
            "má»—i cáº£nh cÃ³ hÃ¬nh ná»n Ä‘áº¹p vÃ  chá»¯ trÃ¬nh bÃ y rÃµ rÃ ng."
        )
        self.prompt_input.setMinimumHeight(150)
        input_layout.addWidget(self.prompt_input)
        input_group.setLayout(input_layout)
        left_layout.addWidget(input_group)

        # â”€â”€ NÃºt báº¯t Ä‘áº§u â”€â”€
        self.btn_start = QPushButton("ðŸš€ Báº¯t Ä‘áº§u táº¡o Video")
        self.btn_start.setObjectName("startButton")
        self.btn_start.setMinimumHeight(50)
        self.btn_start.clicked.connect(self._start_generation)
        left_layout.addWidget(self.btn_start)

        # â”€â”€ Giai Ä‘oáº¡n hiá»‡n táº¡i â”€â”€
        self.stage_label = QLabel("â³ Sáºµn sÃ ng")
        self.stage_label.setObjectName("stageLabel")
        self.stage_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.stage_label)

        # â”€â”€ Progress bar â”€â”€
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        left_layout.addWidget(self.progress_bar)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # === Panel pháº£i: Log ===
        log_group = QGroupBox("ðŸ“‹ Nháº­t kÃ½ tiáº¿n trÃ¬nh")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_output)

        # NÃºt xÃ³a log
        btn_clear_log = QPushButton("ðŸ—‘ï¸ XÃ³a log")
        btn_clear_log.clicked.connect(self.log_output.clear)
        log_layout.addWidget(btn_clear_log)

        log_group.setLayout(log_layout)
        splitter.addWidget(log_group)

        splitter.setSizes([450, 450])
        main_layout.addWidget(splitter)

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Stylesheet
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Load mÃ´ hÃ¬nh Ollama
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _load_ollama_models(self):
        """Gá»i API Ollama cá»¥c bá»™ Ä‘á»ƒ láº¥y danh sÃ¡ch model."""
        self.model_combo.clear()
        try:
            import ollama
            response = ollama.list()
            models = response.get("models", [])
            if not models:
                self.model_combo.addItem("(KhÃ´ng tÃ¬m tháº¥y mÃ´ hÃ¬nh)")
                self._append_log("âš ï¸ KhÃ´ng tÃ¬m tháº¥y mÃ´ hÃ¬nh Ollama. HÃ£y pull model trÆ°á»›c.")
                return
            for m in models:
                name = m.get("name", m.get("model", "unknown"))
                size_gb = m.get("size", 0) / (1024**3)
                display = f"{name} ({size_gb:.1f} GB)" if size_gb > 0 else name
                self.model_combo.addItem(display, name)
            self._append_log(f"âœ… ÄÃ£ táº£i {len(models)} mÃ´ hÃ¬nh Ollama.")
        except Exception as e:
            self.model_combo.addItem("(Lá»—i káº¿t ná»‘i Ollama)")
            self._append_log(f"âŒ Lá»—i káº¿t ná»‘i Ollama: {e}")
            self._append_log("ðŸ’¡ HÃ£y Ä‘áº£m báº£o Ollama Ä‘ang cháº¡y (ollama serve).")

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Duyá»‡t thÆ° má»¥c output
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _current_ai_mode(self) -> str:
        return self.ai_mode_combo.currentData() or "local"

    def _is_online_mode(self) -> bool:
        return self._current_ai_mode() == "online"

    def _update_ai_mode_controls(self):
        online = self._is_online_mode()
        local_widgets = [
            self.ollama_model_label,
            self.model_combo,
            self.btn_refresh_models,
            self.fooocus_url_label,
            self.fooocus_url_input,
            self.fooocus_dir_label,
            self.fooocus_dir_input,
            self.btn_fooocus_dir,
            self.fooocus_cmd_label,
            self.fooocus_cmd_input,
            self.btn_start_fooocus_api,
        ]
        online_widgets = [
            self.online_model_label,
            self.online_model_combo,
            self.online_parallel_label,
            self.online_parallel_spin,
            self.ima2_url_label,
            self.ima2_url_input,
            self.btn_start_ima2,
            self.btn_chatgpt_login,
        ]
        for widget in local_widgets:
            widget.setVisible(not online)
            widget.setEnabled(not online)
        for widget in online_widgets:
            widget.setVisible(online)
            widget.setEnabled(online)
        if online:
            self.fooocus_checkbox.setText("Dung ima2-gen tao anh minh hoa + subtitle")
            self.fooocus_checkbox.setToolTip("Online image-story mode uses ChatGPT/ima2-gen images, subtitle, and audio")
        else:
            self.fooocus_checkbox.setText("DÃ¹ng Fooocus táº¡o áº£nh minh há»a + subtitle")
            self.fooocus_checkbox.setToolTip("Báº­t nhÃ¡nh táº¡o video chá»‰ gá»“m áº£nh Fooocus, subtitle rÃµ nÃ©t vÃ  audio")

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chá»n thÆ° má»¥c xuáº¥t video")
        if folder:
            self.output_label.setText(folder)

    def _browse_music(self):
        """Chá»n file nháº¡c ná»n."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chá»n file nháº¡c ná»n",
            "", "Audio Files (*.mp3 *.wav *.ogg *.m4a *.flac);;All Files (*)"
        )
        if file_path:
            self.music_path_input.setText(file_path)
            self._append_log(f"ðŸŽµ ÄÃ£ chá»n nháº¡c ná»n: {os.path.basename(file_path)}")

    def _browse_fooocus_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Chá»n thÆ° má»¥c Fooocus/Fooocus-API")
        if folder:
            self.fooocus_dir_input.setText(folder)
            self._append_log(f"ðŸ–¼ï¸ ÄÃ£ chá»n thÆ° má»¥c Fooocus API: {folder}")

    def _login_chatgpt(self):
        try:
            from module_ima2_runtime import run_chatgpt_login

            pid = run_chatgpt_login()
            self._append_log(f"Opened ChatGPT/Codex login in a terminal (pid={pid}).")
            self._append_log("After login completes, start ima2 or run the pipeline again.")
        except Exception as e:
            QMessageBox.warning(self, "ChatGPT login failed", f"Could not start login command:\n{e}")

    def _start_ima2_server(self):
        api_url = self.ima2_url_input.text().strip() or "http://127.0.0.1:3333"
        self.btn_start_ima2.setEnabled(False)
        self.btn_start_ima2.setText("Starting")
        self._append_log("Starting ima2-gen server with: npx --yes ima2-gen serve")

        def worker():
            try:
                from module_ima2_runtime import is_ima2_server_ready, launch_ima2_server, wait_for_ima2_server

                if is_ima2_server_ready(api_url):
                    self.signals.log_message.emit(f"ima2-gen is already ready: {api_url}")
                    self.signals.stage_update.emit("ima2-gen ready")
                    return

                launch_ima2_server()
                if wait_for_ima2_server(api_url, timeout_sec=180):
                    self.signals.log_message.emit(f"ima2-gen is ready: {api_url}")
                    self.signals.stage_update.emit("ima2-gen ready")
                else:
                    self.signals.log_message.emit(
                        "ima2-gen was started, but the app could not connect yet. "
                        "Check the ima2 terminal or ~/.ima2/server.json for the actual port."
                    )
                    self.signals.stage_update.emit("ima2-gen not reachable")
            except Exception as e:
                self.signals.log_message.emit(f"Could not start ima2-gen: {e}")
                self.signals.stage_update.emit("ima2-gen startup error")
            finally:
                self.signals.ima2_button_update.emit(True, "Start ima2")

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_ima2_ready(self, api_url: str):
        from module_ima2_runtime import is_ima2_server_ready, launch_ima2_server, wait_for_ima2_server

        api_url = (api_url or "http://127.0.0.1:3333").strip()
        if is_ima2_server_ready(api_url):
            self.signals.log_message.emit(f"ima2-gen is ready: {api_url}")
            return

        self.signals.log_message.emit("ima2-gen is not running. Starting npx --yes ima2-gen serve...")
        launch_ima2_server()
        if not wait_for_ima2_server(api_url, timeout_sec=180):
            raise RuntimeError(
                "ima2-gen did not become reachable. Check the ima2 terminal, then run "
                "`npx @openai/codex login` if OAuth is missing or expired."
            )
        self.signals.log_message.emit(f"ima2-gen is ready: {api_url}")

    def _start_fooocus_api(self):
        """Khá»Ÿi Ä‘á»™ng Fooocus API trong console riÃªng vÃ  chá» endpoint sáºµn sÃ ng."""
        api_dir = self.fooocus_dir_input.text().strip()
        api_url = self.fooocus_url_input.text().strip() or "http://127.0.0.1:8888"
        command = self.fooocus_cmd_input.text().strip()

        if not api_dir or not os.path.isdir(api_dir):
            QMessageBox.warning(
                self,
                "Thiáº¿u thÆ° má»¥c Fooocus API",
                "Vui lÃ²ng chá»n thÆ° má»¥c chá»©a Fooocus-API/Fooocus trÆ°á»›c khi khá»Ÿi Ä‘á»™ng API."
            )
            return
        if not command:
            QMessageBox.warning(self, "Thiáº¿u lá»‡nh cháº¡y", "Vui lÃ²ng nháº­p lá»‡nh khá»Ÿi Ä‘á»™ng Fooocus API.")
            return

        command = self._normalize_fooocus_command(api_dir, command)
        self.fooocus_cmd_input.setText(command)

        self.btn_start_fooocus_api.setEnabled(False)
        self.btn_start_fooocus_api.setText("â³ API")
        self._append_log(f"ðŸ–¼ï¸ Khá»Ÿi Ä‘á»™ng Fooocus API táº¡i: {api_dir}")
        self._append_log(f"â–¶ {command}")

        def worker():
            try:
                if self._is_fooocus_api_ready(api_url):
                    self.signals.log_message.emit(f"âœ… Fooocus API Ä‘ang cháº¡y sáºµn: {api_url}")
                    self.signals.stage_update.emit("âœ… Fooocus API sáºµn sÃ ng")
                    return

                self._launch_fooocus_api_process(api_dir, command)

                if self._wait_for_fooocus_api(api_url, timeout_sec=900):
                    self.signals.log_message.emit(f"âœ… Fooocus API Ä‘Ã£ sáºµn sÃ ng: {api_url}")
                    self.signals.stage_update.emit("âœ… Fooocus API sáºµn sÃ ng")
                else:
                    self.signals.log_message.emit(
                        f"âš ï¸ ÄÃ£ má»Ÿ tiáº¿n trÃ¬nh API nhÆ°ng chÆ°a káº¿t ná»‘i Ä‘Æ°á»£c {api_url}. "
                        "HÃ£y xem cá»­a sá»• Fooocus API Ä‘á»ƒ kiá»ƒm tra lá»—i hoáº·c chá»‰nh láº¡i endpoint/lá»‡nh cháº¡y."
                    )
                    self.signals.stage_update.emit("âš ï¸ ChÆ°a káº¿t ná»‘i Ä‘Æ°á»£c Fooocus API")
            except Exception as e:
                self.signals.log_message.emit(f"âŒ KhÃ´ng khá»Ÿi Ä‘á»™ng Ä‘Æ°á»£c Fooocus API: {e}")
                self.signals.stage_update.emit("âŒ Lá»—i khá»Ÿi Ä‘á»™ng Fooocus API")
            finally:
                self.signals.fooocus_api_button_update.emit(True, "â–¶ API")

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
            self.signals.log_message.emit(f"âœ… Fooocus API Ä‘ang cháº¡y sáºµn: {api_url}")
            return

        if not api_dir or not os.path.isdir(api_dir):
            raise RuntimeError(
                "Fooocus API chÆ°a cháº¡y vÃ  chÆ°a cÃ³ thÆ° má»¥c API há»£p lá»‡. "
                "HÃ£y chá»n thÆ° má»¥c engines\\Fooocus-API hoáº·c báº¥m nÃºt API trÆ°á»›c."
            )

        command = self._normalize_fooocus_command(api_dir, command)
        self.signals.log_message.emit("â„¹ï¸ Fooocus API chÆ°a cháº¡y, app sáº½ tá»± khá»Ÿi Ä‘á»™ng engine ná»™i bá»™.")
        self.signals.log_message.emit(f"ðŸ–¼ï¸ ThÆ° má»¥c API: {api_dir}")
        self.signals.log_message.emit(f"â–¶ {command}")
        self._launch_fooocus_api_process(api_dir, command)

        if not self._wait_for_fooocus_api(api_url, timeout_sec=900):
            raise RuntimeError(
                f"ÄÃ£ má»Ÿ Fooocus API nhÆ°ng chÆ°a káº¿t ná»‘i Ä‘Æ°á»£c {api_url}. "
                "HÃ£y xem cá»­a sá»• Fooocus API Ä‘á»ƒ kiá»ƒm tra cÃ i dependency/model hoáº·c lá»—i CUDA/Torch."
            )
        self.signals.log_message.emit(f"âœ… Fooocus API Ä‘Ã£ sáºµn sÃ ng: {api_url}")

    def _wait_for_fooocus_api(self, api_url: str, timeout_sec: int = 90) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self._is_fooocus_api_ready(api_url):
                return True
            time.sleep(2)
        return False

    def _load_voices(self):
        """Táº£i danh sÃ¡ch giá»ng nÃ³i tá»« VieNeu-TTS."""
        self.voice_combo.clear()
        self.voice_combo.addItem("(Giá»ng máº·c Ä‘á»‹nh)", None)
        self._append_log("ðŸ”„ Äang táº£i danh sÃ¡ch giá»ng nÃ³i...")
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
            self._append_log(f"âœ… ÄÃ£ táº£i {len(voices)} giá»ng nÃ³i")
        except Exception as e:
            self._append_log(f"âš ï¸ KhÃ´ng thá»ƒ táº£i giá»ng nÃ³i: {e}")
            self._append_log("ðŸ’¡ Sáº½ sá»­ dá»¥ng giá»ng máº·c Ä‘á»‹nh khi táº¡o video")

    def _test_tts(self):
        """Táº¡o thá»­ má»™t Ä‘oáº¡n audio ngáº¯n báº±ng cáº¥u hÃ¬nh TTS hiá»‡n táº¡i."""
        tts_mode = self.tts_mode_combo.currentData() or "standard"
        voice_id = self.voice_combo.currentData()
        sample_text = "ÄÃ¢y lÃ  Ä‘oáº¡n kiá»ƒm tra giá»ng nÃ³i cá»§a AI Video Creator."

        def worker():
            try:
                from module_audio_agent import AudioAgent

                self.signals.stage_update.emit("ðŸ”Š Äang test TTS...")
                audio_agent = AudioAgent(self.signals, mode=tts_mode)
                output_path = audio_agent.test_tts_sample(sample_text, voice_id=voice_id)
                self.signals.log_message.emit(f"âœ… Thá»­ TTS hoÃ n táº¥t: {output_path}")
                self.signals.stage_update.emit("âœ… Thá»­ TTS thÃ nh cÃ´ng")
            except Exception as e:
                self.signals.log_message.emit(f"âŒ Thá»­ TTS tháº¥t báº¡i: {e}")
                self.signals.stage_update.emit("âŒ Thá»­ TTS lá»—i")

        threading.Thread(target=worker, daemon=True).start()

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Báº¯t Ä‘áº§u quÃ¡ trÃ¬nh táº¡o video
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _start_generation(self):
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Thiáº¿u thÃ´ng tin", "Vui lÃ²ng nháº­p Ã½ tÆ°á»Ÿng video!")
            return

        ai_mode = self._current_ai_mode()
        online_model = self.online_model_combo.currentData() or "gpt-5.4-mini"
        model_name = online_model if ai_mode == "online" else self.model_combo.currentData()
        if ai_mode != "online" and not model_name:
            QMessageBox.warning(self, "Thiáº¿u mÃ´ hÃ¬nh", "Vui lÃ²ng chá»n mÃ´ hÃ¬nh Ollama!")
            return

        # Disable nÃºt vÃ  reset
        self.btn_start.setEnabled(False)
        self.btn_start.setText("â³ Äang xá»­ lÃ½...")
        self.progress_bar.setValue(0)
        self.log_output.clear()

        max_slides = self.slide_spinbox.value()
        output_dir = self.output_label.text()
        os.makedirs(output_dir, exist_ok=True)

        # Thu tháº­p cÃ¡c tÃ¹y chá»n má»›i
        resolution = self.resolution_combo.currentData() or (1280, 720)
        render_profile = self.render_profile_combo.currentData() or "fast"
        style_preset = self.style_combo.currentData() or "modern"
        output_language = self.language_combo.currentData() or "vi"
        tts_mode = self.tts_mode_combo.currentData() or "standard"
        voice_id = self.voice_combo.currentData()  # None = giá»ng máº·c Ä‘á»‹nh
        music_path = self.music_path_input.text().strip() or None
        music_volume = self.music_volume_spin.value() / 100.0  # 0.0 - 1.0
        resume_enabled = self.resume_checkbox.isChecked()
        fooocus_enabled = self.fooocus_checkbox.isChecked()
        fooocus_url = self.fooocus_url_input.text().strip() or "http://127.0.0.1:8888"
        fooocus_dir = self.fooocus_dir_input.text().strip()
        fooocus_command = self.fooocus_cmd_input.text().strip()
        ima2_url = self.ima2_url_input.text().strip() or "http://127.0.0.1:3333"
        online_parallel = self.online_parallel_spin.value()

        # Cháº¡y pipeline trong thread riÃªng
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(prompt, model_name, max_slides, output_dir,
                  resolution, style_preset, output_language, tts_mode, voice_id, music_path, music_volume,
                  resume_enabled, fooocus_enabled, fooocus_url, fooocus_dir, fooocus_command, ai_mode, ima2_url, online_parallel,
                  render_profile),
            daemon=True
        )
        thread.start()

    def _run_image_story_scene_pipeline(
        self,
        plan,
        image_agent,
        audio_agent,
        subtitle_agent,
        output_dir,
        resolution,
        voice_id,
        resume_enabled,
        online_mode,
        asset_workers,
        fast_mode,
        music_path,
        music_volume,
    ):
        from video_assembler import VideoAssembler

        slides = list(getattr(plan, "slides", []) or [])
        total = len(slides)
        if total == 0:
            raise RuntimeError("Káº¿ hoáº¡ch video khÃ´ng cÃ³ cáº£nh nÃ o Ä‘á»ƒ dá»±ng.")

        if fast_mode:
            self.signals.log_message.emit("âš¡ Fast mode: dÃ¹ng subtitle fallback, encode veryfast, cache part theo tá»«ng cáº£nh.")
        else:
            self.signals.log_message.emit("ðŸŽšï¸ Final mode: váº«n dá»±ng part theo tá»«ng cáº£nh nhÆ°ng giá»¯ cháº¥t lÆ°á»£ng encode cao.")

        assembler = VideoAssembler(self.signals)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "ima2_fast_video" if online_mode and fast_mode else "ima2_video" if online_mode else "fooocus_fast_video" if fast_mode else "fooocus_video"
        output_path = os.path.join(output_dir, f"{prefix}_{timestamp}.mp4")
        image_workers = max(1, int(asset_workers or 1)) if online_mode else 1
        image_workers = min(image_workers, int(getattr(image_agent, "MAX_IMAGE_WORKERS", image_workers) or image_workers))

        image_files = [None] * total
        audio_files = [None] * total
        subtitle_cues = [None] * total
        part_paths = [None] * total
        render_futures = {}

        def maybe_render(idx, render_executor):
            if (
                image_files[idx]
                and audio_files[idx]
                and subtitle_cues[idx] is not None
                and idx not in render_futures.values()
                and part_paths[idx] is None
            ):
                slide_num = idx + 1
                part_path = os.path.join(
                    assembler.TEMP_MERGE_DIR,
                    f"image_story_{'fast' if fast_mode else 'final'}_part_{slide_num}.mp4",
                )
                frame_path = os.path.join(
                    assembler.TEMP_MERGE_DIR,
                    f"image_story_{'fast' if fast_mode else 'final'}_bg_{slide_num}.png",
                )
                future = render_executor.submit(
                    assembler.render_image_story_part,
                    slide_num,
                    image_files[idx],
                    audio_files[idx],
                    subtitle_cues[idx],
                    resolution,
                    total,
                    part_path,
                    frame_path,
                    fast_mode,
                    resume_enabled,
                )
                render_futures[future] = idx

        self.signals.stage_update.emit("âš¡ Táº¡o asset vÃ  dá»±ng tá»«ng cáº£nh ngay khi sáºµn sÃ ng...")
        with ThreadPoolExecutor(max_workers=image_workers) as image_executor, \
                ThreadPoolExecutor(max_workers=1) as audio_executor, \
                ThreadPoolExecutor(max_workers=1) as render_executor:
            futures = {}
            for idx, slide in enumerate(slides):
                slide_num = idx + 1
                futures[image_executor.submit(
                    image_agent.generate_image_for_slide,
                    slide,
                    slide_num,
                    total,
                    resume_enabled,
                )] = ("image", idx)
                futures[audio_executor.submit(
                    audio_agent.generate_audio_for_slide,
                    str(getattr(slide, "narration", "") or ""),
                    slide_num,
                    total,
                    voice_id,
                    resume_enabled,
                )] = ("audio", idx)

            completed_assets = 0
            for future in as_completed(futures):
                kind, idx = futures[future]
                if kind == "image":
                    image_files[idx] = future.result()
                else:
                    audio_files[idx] = future.result()
                    if fast_mode:
                        subtitle_cues[idx] = subtitle_agent.fallback_for_slide(slides[idx], audio_files[idx])
                    else:
                        duration = subtitle_agent._audio_duration(audio_files[idx])
                        subtitle_cues[idx] = subtitle_agent.generate_for_slide(slides[idx], duration)

                completed_assets += 1
                progress = 25 + int(35 * completed_assets / max(1, total * 2))
                self.signals.progress_update.emit(min(60, progress))
                maybe_render(idx, render_executor)

            rendered = 0
            for future in as_completed(render_futures):
                idx = render_futures[future]
                part_paths[idx] = future.result()
                rendered += 1
                progress = 60 + int(25 * rendered / max(1, total))
                self.signals.progress_update.emit(min(85, progress))

        merged_parts = [path for path in part_paths if path]
        self.signals.stage_update.emit("ðŸŽ¬ Ná»‘i cÃ¡c cáº£nh Ä‘Ã£ dá»±ng...")
        return assembler.finalize_image_story_parts(
            merged_parts,
            output_path,
            bg_music_path=music_path,
            bg_music_volume=music_volume,
            fast_mode=fast_mode,
        )

    def _run_pipeline(self, prompt, model_name, max_slides, output_dir,
                      resolution, style_preset, output_language, tts_mode, voice_id, music_path, music_volume,
                      resume_enabled=False, fooocus_enabled=False, fooocus_url="http://127.0.0.1:8888",
                      fooocus_dir="", fooocus_command="start_fooocus_api.bat", ai_mode="local",
                      ima2_url="http://127.0.0.1:3333", online_parallel=4, render_profile="fast"):
        """Pipeline chÃ­nh cháº¡y trong background thread."""
        try:
            from module_video_agent import VideoAgent, VideoPlan
            from module_audio_agent import AudioAgent
            from video_assembler import VideoAssembler
            from module_ai_providers import Ima2ChatGPTTextProvider, LocalOllamaTextProvider

            fast_mode = (render_profile or "fast") == "fast"
            original_resolution = resolution
            resolution = self._fast_preview_resolution(resolution) if fast_mode else resolution
            width, height = resolution
            render_mode = "Fooocus image story" if fooocus_enabled else "HTML static slides"
            profile_label = "Fast preview" if fast_mode else "Final quality"
            self.signals.log_message.emit(f"âš™ï¸ Cáº¥u hÃ¬nh: {width}x{height}, Profile={profile_label}, Cháº¿ Ä‘á»™={render_mode}, Phong cÃ¡ch={style_preset}, NgÃ´n ngá»¯={output_language}, TTS={tts_mode}, Nháº¡c={'CÃ³' if music_path else 'KhÃ´ng'}")
            if fast_mode and resolution != original_resolution:
                self.signals.log_message.emit(f"âš¡ Fast mode: render preview {original_resolution[0]}x{original_resolution[1]} â†’ {width}x{height}")
            online_mode = ai_mode == "online"
            asset_workers = max(1, int(online_parallel or 1)) if online_mode else 2
            if online_mode:
                self.signals.stage_update.emit("Checking ima2-gen / ChatGPT...")
                self._ensure_ima2_ready(ima2_url)
                text_provider = Ima2ChatGPTTextProvider(model_name, server_url=ima2_url)
            else:
                text_provider = LocalOllamaTextProvider(model_name)
            image_engine = "ima2-gen" if online_mode else "Fooocus"
            render_mode = f"{image_engine} image story" if fooocus_enabled else "HTML static slides"
            self.signals.log_message.emit(f"AI mode={ai_mode}, model={model_name}, render={render_mode}")
            if resume_enabled:
                self.signals.log_message.emit("ðŸ” Resume Ä‘ang báº­t: dÃ¹ng láº¡i file táº¡m há»£p lá»‡ náº¿u cÃ³.")

            # â”€â”€ Giai Ä‘oáº¡n 1: Brainstorming â”€â”€
            self.signals.stage_update.emit("ðŸ§  Giai Ä‘oáº¡n 1/5: LÃªn Ã½ tÆ°á»Ÿng...")
            self.signals.progress_update.emit(5)

            video_agent = VideoAgent(
                model_name,
                self.signals,
                resolution=resolution,
                style_preset=style_preset,
                output_language=output_language,
                text_provider=text_provider,
                ai_mode=ai_mode,
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
                        raise ValueError("NgÃ´n ngá»¯ cá»§a plan cÅ© khÃ´ng khá»›p cáº¥u hÃ¬nh hiá»‡n táº¡i")
                    if plan_meta.get("plan_cache_version") != 2:
                        raise ValueError("Plan cache version cu khong khop")
                    if plan_meta.get("ai_mode", "local") != ai_mode or plan_meta.get("model_name") != model_name:
                        raise ValueError("AI mode/model cua plan cu khong khop cau hinh hien tai")
                    with open(plan_path, "r", encoding="utf-8") as f:
                        plan = VideoPlan.model_validate_json(f.read())
                    self.signals.log_message.emit(f"âœ… ÄÃ£ táº£i láº¡i káº¿ hoáº¡ch cÅ©: {plan_path}")
                except Exception as e:
                    self.signals.log_message.emit(f"âš ï¸ KhÃ´ng Ä‘á»c Ä‘Æ°á»£c plan cÅ©, sáº½ brainstorm láº¡i: {e}")

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
                            "plan_cache_version": 2,
                            "ai_mode": ai_mode,
                            "model_name": model_name,
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
                self.signals.log_message.emit(f"ðŸ’¾ ÄÃ£ lÆ°u káº¿ hoáº¡ch Ä‘á»ƒ resume: {plan_path}")
            self.signals.progress_update.emit(15)

            # Kiá»ƒm tra TTS trÆ°á»›c khi tá»‘n thá»i gian render.
            self.signals.stage_update.emit("ðŸ”Š Kiá»ƒm tra TTS trÆ°á»›c khi render...")
            audio_agent = AudioAgent(self.signals, mode=tts_mode)
            sample_text = plan.slides[0].narration if plan.slides else "Kiá»ƒm tra giá»ng nÃ³i."
            try:
                audio_agent.test_tts_sample(sample_text[:220], voice_id=voice_id)
            except Exception as e:
                raise RuntimeError(
                    f"Thá»­ TTS tháº¥t báº¡i vá»›i cháº¿ Ä‘á»™ '{tts_mode}'. "
                    "HÃ£y thá»­ Ä‘á»•i sang Turbo hoáº·c kiá»ƒm tra VieNeu/llama-cpp trÆ°á»›c khi render video.\n"
                    f"Chi tiáº¿t: {e}"
                ) from e
            self.signals.progress_update.emit(25)

            if fooocus_enabled:
                from module_subtitle_agent import SubtitleAgent

                if online_mode:
                    from module_ima2_image_agent import Ima2ImageAgent

                    self.signals.stage_update.emit("Stage 2/5: Creating images with ima2-gen...")
                    image_agent = Ima2ImageAgent(
                        ima2_url,
                        self.signals,
                        resolution=resolution,
                        style_preset=style_preset,
                        model_name=model_name,
                    )
                else:
                    from module_fooocus_agent import FooocusAgent

                    self.signals.stage_update.emit("ðŸ–¼ï¸ Kiá»ƒm tra / khá»Ÿi Ä‘á»™ng Fooocus API...")
                    self._ensure_fooocus_api_ready(fooocus_url, fooocus_dir, fooocus_command)

                    self.signals.stage_update.emit("ðŸŽ¨ Giai Ä‘oáº¡n 2/5: Táº¡o áº£nh minh há»a báº±ng Fooocus...")
                    image_agent = FooocusAgent(
                        fooocus_url,
                        self.signals,
                        resolution=resolution,
                        style_preset=style_preset,
                    )
                self.signals.stage_update.emit("âš¡ Táº¡o áº£nh vÃ  audio song song...")
                audio_agent = AudioAgent(self.signals, mode=tts_mode)
                output_path = self._run_image_story_scene_pipeline(
                    plan=plan,
                    image_agent=image_agent,
                    audio_agent=audio_agent,
                    subtitle_agent=SubtitleAgent(
                        model_name,
                        self.signals,
                        fps=30,
                        output_language=output_language,
                        resolution=resolution,
                        text_provider=text_provider,
                        ai_mode=ai_mode,
                    ),
                    output_dir=output_dir,
                    resolution=resolution,
                    voice_id=voice_id,
                    resume_enabled=resume_enabled,
                    online_mode=online_mode,
                    asset_workers=asset_workers,
                    fast_mode=fast_mode,
                    music_path=music_path,
                    music_volume=music_volume,
                )
                self.signals.progress_update.emit(100)
                self.signals.finished.emit(output_path)
                return

            # â”€â”€ Giai Ä‘oáº¡n 2: Viáº¿t HTML/CSS â”€â”€
            self.signals.stage_update.emit("ðŸ’» Giai Ä‘oáº¡n 2/5: Viáº¿t HTML/CSS cho cÃ¡c cáº£nh...")
            audio_agent = AudioAgent(self.signals, mode=tts_mode)
            narrations = [slide.narration for slide in plan.slides]
            audio_executor = ThreadPoolExecutor(max_workers=1)
            audio_future = audio_executor.submit(
                audio_agent.generate_audio,
                narrations,
                voice_id=voice_id,
                resume=resume_enabled,
            )
            html_files = video_agent.generate_html_slides(
                plan,
                resume=resume_enabled,
                max_workers=asset_workers if online_mode else 1,
            )
            self.signals.progress_update.emit(35)
            self.signals.stage_update.emit("ðŸ–¼ï¸ Xuáº¥t áº£nh xem trÆ°á»›c PNG cho cÃ¡c cáº£nh...")
            preview_files = video_agent.render_preview_images(html_files, resume=resume_enabled)
            self.signals.log_message.emit(
                f"ðŸ–¼ï¸ Preview PNG Ä‘Ã£ sáºµn sÃ ng: {os.path.abspath(video_agent.PREVIEW_DIR)} ({len(preview_files)} file)"
            )
            self.signals.progress_update.emit(42)

            # â”€â”€ Giai Ä‘oáº¡n 3: Render cáº£nh â†’ video â”€â”€
            self.signals.stage_update.emit("ðŸŽ¥ Giai Ä‘oáº¡n 3/5: Render cÃ¡c cáº£nh thÃ nh video...")
            durations = [slide.duration_seconds for slide in plan.slides]
            video_clips = video_agent.render_slides_to_video(html_files, durations=durations, resume=resume_enabled)
            self.signals.progress_update.emit(55)

            # â”€â”€ Giai Ä‘oáº¡n 4: TTS Audio â”€â”€
            self.signals.stage_update.emit("ðŸ”Š Giai Ä‘oáº¡n 4/5: Táº¡o giá»ng nÃ³i TTS...")
            audio_files = audio_future.result()
            audio_executor.shutdown(wait=True)
            self.signals.progress_update.emit(75)

            # â”€â”€ Giai Ä‘oáº¡n 5: Merging â”€â”€
            self.signals.stage_update.emit("ðŸ”§ Giai Ä‘oáº¡n 5/5: GhÃ©p video + Ã¢m thanh...")
            assembler = VideoAssembler(self.signals)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"video_{timestamp}.mp4")
            assembler.assemble(
                video_clips, audio_files, output_path,
                bg_music_path=music_path,
                bg_music_volume=music_volume,
                fast_mode=fast_mode,
            )
            self.signals.progress_update.emit(100)

            self.signals.finished.emit(output_path)

        except Exception as e:
            import traceback
            self.signals.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Slots (nháº­n signal tá»« worker thread)
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _append_log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{timestamp}] {msg}")
        # Auto-scroll xuá»‘ng
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_progress(self, value: int):
        self.progress_bar.setValue(value)

    def _update_stage(self, stage: str):
        self.stage_label.setText(stage)
        self._append_log(f"â”â”â” {stage} â”â”â”")

    def _update_fooocus_api_button(self, enabled: bool, text: str):
        self.btn_start_fooocus_api.setEnabled(enabled)
        self.btn_start_fooocus_api.setText(text)

    def _update_ima2_button(self, enabled: bool, text: str):
        self.btn_start_ima2.setEnabled(enabled)
        self.btn_start_ima2.setText(text)

    def _on_finished(self, output_path: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("ðŸš€ Báº¯t Ä‘áº§u táº¡o Video")
        self.stage_label.setText("âœ… HoÃ n thÃ nh!")
        self._append_log(f"ðŸŽ‰ Video Ä‘Ã£ táº¡o xong: {output_path}")
        QMessageBox.information(
            self, "ThÃ nh cÃ´ng!",
            f"Video Ä‘Ã£ Ä‘Æ°á»£c táº¡o thÃ nh cÃ´ng!\n\nðŸ“ {output_path}"
        )

    def _on_error(self, error_msg: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("ðŸš€ Báº¯t Ä‘áº§u táº¡o Video")
        self.stage_label.setText("âŒ Lá»—i!")
        self._append_log(f"âŒ Lá»–I: {error_msg}")
        QMessageBox.critical(self, "Lá»—i", f"ÄÃ£ xáº£y ra lá»—i:\n\n{error_msg[:500]}")
    @staticmethod
    def _fast_preview_resolution(resolution):
        width, height = resolution
        longest = max(width, height)
        if longest <= 1280:
            return resolution
        scale = 1280 / longest
        fast_width = max(2, int(round(width * scale / 2) * 2))
        fast_height = max(2, int(round(height * scale / 2) * 2))
        return fast_width, fast_height


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Entry point
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette bá»• sung
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
