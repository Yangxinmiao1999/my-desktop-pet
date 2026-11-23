"""字号设置对话框 - 可调显示字号（计时器）与对话字号（气泡/聊天窗口）"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from utils.config_loader import ConfigLoader

FONT_FAMILY = "Microsoft YaHei UI"

# 皮卡丘黄主题（与 ui/pet.py 保持一致）
PIKACHU_YELLOW = "#FFD93D"
PIKACHU_YELLOW_HOVER = "#FFC107"
PIKACHU_YELLOW_EDGE = "#E8B800"
TEXT_ON_PRIMARY = "#FFFFFF"

# 字号允许范围（pt）
MIN_PT = 8
MAX_PT = 48


class FontSizeDialog(QDialog):
    """字号设置对话框

    - 显示字号：宠物头顶的计时器数字
    - 对话字号：宠物头顶气泡 + 聊天窗口正文

    确定：写入 config.yaml 的 ui.display_font_pt / ui.chat_font_pt
    """

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("字号设置")
        self.setFixedSize(420, 230)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        ui_conf = config.get("ui", {})
        display_pt = int(ui_conf.get("display_font_pt", 24))
        chat_pt = int(ui_conf.get("chat_font_pt", 20))

        self.setStyleSheet(f"""
            QDialog {{
                background-color: #FFFFFF;
            }}
            QLabel {{
                color: #2B2B2B;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                background: transparent;
            }}
            QSpinBox {{
                border: 1px solid {PIKACHU_YELLOW_EDGE};
                border-radius: 6px;
                padding: 4px 8px;
                font-family: {FONT_FAMILY};
                font-size: 14px;
                background: #FFFDF5;
                color: #2B2B2B;
            }}
            QSpinBox:focus {{
                border: 2px solid {PIKACHU_YELLOW};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 18)

        # 表单：两行字号
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.display_spin = QSpinBox()
        self.display_spin.setRange(MIN_PT, MAX_PT)
        self.display_spin.setValue(display_pt)
        self.display_spin.setSuffix(" pt")
        self.display_spin.setToolTip("宠物头顶计时器数字的字号")
        form.addRow("显示字号（计时器）", self.display_spin)

        self.chat_spin = QSpinBox()
        self.chat_spin.setRange(MIN_PT, MAX_PT)
        self.chat_spin.setValue(chat_pt)
        self.chat_spin.setSuffix(" pt")
        self.chat_spin.setToolTip("宠物头顶气泡和聊天窗口正文的字号")
        form.addRow("对话字号（气泡/聊天）", self.chat_spin)

        layout.addLayout(form)

        # 说明文字
        hint = QLabel("范围 8–48 pt，保存后立即生效（聊天窗口重新打开后应用）")
        hint.setStyleSheet(f"color: #6B6B6B; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(72, 32)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(self._btn_style("#F5F5F5", "#E8E8E8", "#333333"))
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("保存")
        ok_btn.setFixedSize(72, 32)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet(self._btn_style(PIKACHU_YELLOW, PIKACHU_YELLOW_HOVER, TEXT_ON_PRIMARY))
        ok_btn.clicked.connect(self._save_and_accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _btn_style(normal: str, hover: str, text_color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {normal};
                color: {text_color};
                border: none;
                border-radius: 6px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """

    def _save_and_accept(self):
        """写入配置并关闭"""
        config = ConfigLoader.load()
        ui_conf = config.setdefault("ui", {})
        ui_conf["display_font_pt"] = int(self.display_spin.value())
        ui_conf["chat_font_pt"] = int(self.chat_spin.value())
        ConfigLoader.save(config)
        self.accept()
