"""桌面宠物主窗口模块 - 支持自定义状态"""
import json
import os
import random
import sys
import time
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QMovie, QCursor
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.chat import ChatService
from core.compressor import Compressor
from core.memory import MemoryManager
from core.persona import PersonaManager
from ui.chat_window import ChatWindow
from ui.settings_dialog import SettingsDialog
from utils.config_loader import ConfigLoader
from utils.logger import get_logger, init_logging
from utils.sound import sound_manager
from utils.timer_storage import TimerStorage
from utils.todo_storage import TodoStorage


# 跨平台字体支持
def get_system_font_family():
    """获取跨平台字体族名称"""
    if sys.platform == 'darwin':  # macOS
        return "'PingFang SC', '-apple-system', 'Helvetica Neue', sans-serif"
    elif sys.platform == 'win32':  # Windows
        return "'Microsoft YaHei UI', '微软雅黑', sans-serif"
    else:  # Linux 等
        return "'Noto Sans CJK SC', 'WenQuanYi Micro Hei', sans-serif"

FONT_FAMILY = get_system_font_family()

# 模块日志
log = get_logger("pet")

# ===== 主题：皮卡丘黄 =====
# 主色统一用皮卡丘黄，主色上的文字统一白色
PIKACHU_YELLOW = "#FFD93D"        # 主色 - 皮卡丘黄
PIKACHU_YELLOW_HOVER = "#FFC107"  # 悬停 / 按下 - 深一档
PIKACHU_YELLOW_EDGE = "#E8B800"   # 描边 - 保证白字有边界
PIKACHU_YELLOW_LIGHT = "#FFF9E6"  # 浅底（菜单等大面积区域）
TEXT_ON_PRIMARY = "#FFFFFF"       # 主色上的文字

TIMER_FONT_PT = 24                # 计时器字号（pt）
BUBBLE_FONT_PT = 20               # 对话气泡字号（pt）

# 默认状态配置
DEFAULT_STATES = {
    "idle": {
        "animations": [],  # 空则使用默认目录
        "dialogs": []      # 空则使用默认文件
    },
    "click": {
        "animation": "assets/pika2d/pika2d_idle.gif",
        "dialog": "⚡ 别戳我！",
        "style": f"color: {TEXT_ON_PRIMARY}; background-color: {PIKACHU_YELLOW};"
    },
    "drag": {
        "animation": "",
        "dialog": "✋ 带我飞~",
        "style": f"color: {TEXT_ON_PRIMARY}; background-color: {PIKACHU_YELLOW};"
    },
    "rest": {
        "animation": "",
        "dialog": "⏰ 该休息啦！",
        "style": f"color: {TEXT_ON_PRIMARY}; background-color: {PIKACHU_YELLOW};"
    }
}


class ProfileAnalyzeWorker(QThread):
    """后台分析用户画像线程"""
    finished = pyqtSignal(dict)

    def __init__(self, persona_manager, messages, api_config):
        super().__init__()
        self.persona_manager = persona_manager
        self.messages = messages
        self.api_config = api_config

    def run(self):
        try:
            profile = self.persona_manager.analyze_user_profile(self.messages, self.api_config)
            self.finished.emit(profile)
        except:
            self.finished.emit({})


class DesktopPet(QWidget):
    """桌面宠物 - 支持自定义状态"""

    # 状态名称
    STATE_IDLE = "idle"
    STATE_CLICK = "click"
    STATE_DRAG = "drag"
    STATE_REST = "rest"

    def __init__(self, parent=None):
        super().__init__(parent)
        log.info("初始化桌面宠物...")

        # 加载配置
        self.config = ConfigLoader.load()
        log.debug(f"配置加载完成")

        # 字号（可在「字号设置」对话框中调整，持久化到 config.yaml）
        ui_conf = self.config.get("ui", {})
        self._timer_font_pt = int(ui_conf.get("display_font_pt", TIMER_FONT_PT))
        self._chat_font_pt = int(ui_conf.get("chat_font_pt", BUBBLE_FONT_PT))

        # 初始化核心模块
        self.chat_service = ChatService(self.config)
        self.compressor = Compressor(self.chat_service)
        self.memory_manager = MemoryManager(self.config, self.chat_service, self.compressor)
        self.memory_manager.load_from_file()
        self.persona_manager = PersonaManager(self.config)
        
        # 初始化 MCP（如果启用）
        self._mcp_manager = None
        self._init_mcp()
        
        # 启用 Agent 模式（支持技能调用）
        agent_enabled = self.config.get("agent", {}).get("enabled", True)
        if agent_enabled:
            log.info("启用 Agent 模式，加载技能...")
            self.chat_service.enable_agent_mode(self.persona_manager)
        
        log.info(f"核心模块初始化完成, 宠物名称: {self.persona_manager.name}, Agent模式: {agent_enabled}")

        # 加载状态配置
        self._load_states_config()

        # 状态
        self._current_state = self.STATE_IDLE
        self._rest_enabled = False
        self._drag_pos = None
        self._chat_window = None
        self._settings_dialog = None
        self._pet_size = self.config.get("ui", {}).get("pet_size", 100)
        
        # 读取休息提醒配置
        self._rest_config = self.config.get("rest_reminder", {})
        if self._rest_config.get("enabled", False):
            self._rest_enabled = True
            interval_ms = self._rest_config.get("interval", 3600) * 1000
            self.rest_timer.start(interval_ms)
            log.info(f"休息提醒已启用，间隔: {self._rest_config.get('interval', 3600)}秒")
        
        # 读取待办提醒配置（开关仍来自 config，具体待办从文件加载）
        todo_enabled = self.config.get("todo_reminder", {}).get("enabled", True)
        self._todo_config = {
            "enabled": todo_enabled,
            "todos": TodoStorage.load_todos(),
        }
        self._last_todo_check = {}  # 记录已提醒的待办

        # 计时器状态
        self._timer_running = False
        self._timer_start_dt = None      # 开始时的墙钟时间（用于记录）
        self._timer_start_mono = None    # 开始时的单调时钟（用于算时长，不受系统时间调整影响）
        self._press_global = None        # 按下时的全局坐标
        self._press_moved = False        # 按下后是否发生过拖动

        # 更新系统上下文中的待办事项
        self.persona_manager.update_project_context(todos=self._todo_config.get("todos", []))

        # 初始化窗口
        self._init_window()
        self._init_tray()
        self._init_pet()
        self._init_timers()

    def _init_mcp(self):
        """初始化 MCP 服务"""
        mcp_config = self.config.get("mcp", {})
        if not mcp_config.get("enabled", False):
            log.debug("MCP 功能未启用")
            return
        
        try:
            import asyncio
            from core.mcp_config import MCPConfig, MCPServerConfig
            from core.mcp_client import initialize_mcp
            
            # 构建配置
            servers = []
            server_list = mcp_config.get("servers") or []
            for server_data in server_list:
                if server_data.get("enabled", False):
                    servers.append(MCPServerConfig.from_dict(server_data))
            
            if not servers:
                log.info("没有启用的 MCP 服务器")
                return
            
            config = MCPConfig(enabled=True, servers=servers)
            
            # 异步初始化
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                # 在后台线程中初始化
                import threading
                def init_mcp_async():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    self._mcp_manager = new_loop.run_until_complete(initialize_mcp(config))
                thread = threading.Thread(target=init_mcp_async, daemon=True)
                thread.start()
            else:
                self._mcp_manager = loop.run_until_complete(initialize_mcp(config))
            
            log.info("MCP 初始化完成")
            
        except ImportError as e:
            log.warning(f"MCP SDK 未安装: {e}")
        except Exception as e:
            log.error(f"MCP 初始化失败: {e}")

    def _load_states_config(self):
        """加载状态配置"""
        self.states = {}
        config_states = self.config.get("states", {})

        for state_name in [self.STATE_IDLE, self.STATE_CLICK, self.STATE_DRAG, self.STATE_REST]:
            if state_name in config_states:
                self.states[state_name] = config_states[state_name]
            else:
                self.states[state_name] = DEFAULT_STATES.get(state_name, {})

    def _init_window(self):
        """初始化窗口"""
        # macOS 需要特殊的窗口设置
        if sys.platform == 'darwin':
            # macOS: 使用 Tool 窗口类型，避免被 Dock 和任务栏管理
            self.setWindowFlags(
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.Tool  # macOS 上使用 Tool 而不是 SubWindow
            )
            # macOS 需要设置这个属性才能正确显示透明背景
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            # macOS 上需要设置这个属性确保窗口可以接收鼠标事件
            self.setAttribute(Qt.WA_Hover, True)
        else:
            # Windows/Linux: 使用原有设置
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow
            )
            self.setAutoFillBackground(False)
            self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 设置任务栏图标
        icon_path = "assets/icon.png"
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _init_tray(self):
        """初始化系统托盘"""
        icon_path = "assets/icon.png"
        if not os.path.exists(icon_path):
            icon_path = "icon.png"

        icon = QIcon(icon_path)
        tray_menu = QMenu(self)

        show_action = QAction("显示", self, triggered=self._show_window)
        chat_action = QAction("聊天", self, triggered=self._open_chat)
        timer_action = QAction("⏱ 计时（开始 / 结束）", self, triggered=self._toggle_timer)
        font_action = QAction("字号设置", self, triggered=self._open_font_settings)
        quit_action = QAction("退出", self, triggered=self._quit)

        tray_menu.addAction(show_action)
        tray_menu.addAction(chat_action)
        tray_menu.addAction(timer_action)
        tray_menu.addAction(font_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def _bubble_style(self, extra: str = "") -> str:
        """气泡统一样式：皮卡丘黄底 + 白字（字号可在设置中调整）"""
        return f"""
            QLabel {{
                font-family: {FONT_FAMILY};
                font-size: {self._chat_font_pt}pt;
                font-weight: 600;
                color: {TEXT_ON_PRIMARY};
                background-color: {PIKACHU_YELLOW};
                border: 1px solid {PIKACHU_YELLOW_EDGE};
                border-radius: 10px;
                padding: 6px 12px;
                {extra}
            }}
        """

    def _init_pet(self):
        """初始化宠物"""
        # 计时器标签（默认隐藏，开始计时时出现在头顶）
        self.timer_label = QLabel(self)
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet(self._timer_label_style())
        self.timer_label.setMinimumWidth(150)
        self.timer_label.setText("⏱ 00:00")
        self.timer_label.hide()

        # 对话框标签
        self.talk_label = QLabel(self)
        self.talk_label.setStyleSheet(self._bubble_style())
        self.talk_label.setAlignment(Qt.AlignCenter)
        # 20pt 字比较大，长句需要限宽换行（宽度在 _layout_bubble 里按文本计算）
        self.talk_label.setWordWrap(True)
        self.talk_label.hide()

        # 动画标签
        self.image_label = QLabel(self)
        self._play_animation(self._get_idle_animation())

        # 布局 - 紧凑排列
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)
        layout.addWidget(self.timer_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.talk_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.image_label, alignment=Qt.AlignCenter)

        # 加载资源
        self._load_idle_resources()

        # 设置大小 - 根据内容自适应
        self.adjustSize()
        self._random_position()

    def _get_idle_animation(self):
        """获取待机动画（固定用动作包里的透明呼吸动画，避免扫到黑底素材）"""
        idle_path = "assets/pika2d/actions/idle.gif"
        if os.path.exists(idle_path):
            return idle_path
        idle_path = "pika2d/actions/idle.gif"
        if os.path.exists(idle_path):
            return idle_path
        return "assets/pika2d/actions/idle.gif"

    def _load_idle_resources(self):
        """加载待机资源"""
        # 待机动画：固定用动作包里的透明呼吸动画（不用扫描目录，避免黑底素材混入）
        self.idle_animations = ["assets/pika2d/actions/idle.gif"]

        idle_config = self.states.get(self.STATE_IDLE, {})
        # 加载待机对话列表
        self.idle_dialogs = idle_config.get("dialogs", [])
        if not self.idle_dialogs:
            dialog_file = "assets/dialog.txt"
            if not os.path.exists(dialog_file):
                dialog_file = "dialog.txt"
            try:
                with open(dialog_file, "r", encoding="utf-8") as f:
                    self.idle_dialogs = [line for line in f.read().split("\n") if line.strip()]
            except:
                self.idle_dialogs = ["皮卡皮卡~"]

        # 加载动作包（manifest.json 驱动：程序动画 + AI 视频动作）
        self._actions = {}
        for mf in ("assets/pika2d/actions/manifest.json", "pika2d/actions/manifest.json"):
            if os.path.exists(mf):
                try:
                    with open(mf, "r", encoding="utf-8") as f:
                        self._actions = json.load(f)
                    log.info(f"动作包已加载: {len(self._actions)} 个动作")
                except Exception as exc:
                    log.warning(f"动作包加载失败: {exc}")
                break
        self._action_revert_timer = None

    def _cancel_action_revert(self):
        """取消动作播完自动回待机的定时器"""
        if self._action_revert_timer is not None:
            try:
                self._action_revert_timer.stop()
            except Exception:
                pass
            self._action_revert_timer = None

    def _play_action(self, action_id: str, auto_revert_ms=None):
        """播放动作包里的指定动作

        loop 动作常驻播放（直到用户点击或再选动作）；
        单次动作播完自动回待机。auto_revert_ms 可强制限时回位。
        """
        info = self._actions.get(action_id)
        if not info:
            log.warning(f"未知动作: {action_id}")
            return
        path = os.path.join("assets", "pika2d", info.get("file", ""))
        if not os.path.exists(path):
            log.warning(f"动作文件缺失: {path}")
            return
        self._cancel_action_revert()
        self._current_state = "action"
        self._play_animation(path)
        if not info.get("loop", True):
            auto_revert_ms = info.get("duration_ms", 1000) + 250
        if auto_revert_ms:
            self._action_revert_timer = QTimer(self)
            self._action_revert_timer.setSingleShot(True)
            self._action_revert_timer.timeout.connect(self._reset_to_idle)
            self._action_revert_timer.start(auto_revert_ms)
        log.info(f"播放动作: {action_id}")

    def _play_animation(self, anim_path):
        """播放动画（统一缩放）"""
        if not os.path.exists(anim_path):
            # 兜底：待机呼吸动画（透明背景）
            anim_path = "assets/pika2d/actions/idle.gif"
            if not os.path.exists(anim_path):
                anim_path = "pika2d/actions/idle.gif"
        self.movie = QMovie(anim_path)
        # macOS 兼容性：设置缓存模式以确保动画正常播放
        self.movie.setCacheMode(QMovie.CacheAll)
        self.movie.setScaledSize(QSize(self._pet_size, self._pet_size))
        self.image_label.setMovie(self.movie)
        self.movie.start()

    def _show_state(self, state_name):
        """显示指定状态"""
        state_config = self.states.get(state_name, DEFAULT_STATES.get(state_name, {}))

        # 播放动画
        anim_path = state_config.get("animation", "")
        if anim_path:
            self._play_animation(anim_path)

        # 显示对话
        dialog = state_config.get("dialog", "")
        if dialog:
            anchor = self._pet_anchor()
            self.talk_label.setText(dialog)

            # 应用样式（状态自带样式优先，缺省则用皮卡丘黄气泡）
            style = state_config.get("style", "")
            self.talk_label.setStyleSheet(self._bubble_style(style))

            self._layout_bubble()
            self.talk_label.show()
            self._keep_pet_anchor(anchor)

    def _layout_bubble(self):
        """按文本内容给气泡定宽再调整大小

        20pt 文字较宽：短句保持单行；长句限宽 400px 换行。
        不直接用 adjustSize() 是因为带 wordWrap 的 QLabel 会把宽度
        收得过窄，气泡变成一列细长条。
        """
        label = self.talk_label
        label.ensurePolished()
        text = label.text() or ""
        lines = text.splitlines() or [""]
        fm = label.fontMetrics()
        longest = max(fm.horizontalAdvance(line) for line in lines)
        width = min(longest + 36, 400)  # 36 = 左右 padding + 边框 + 余量
        label.setFixedWidth(max(int(width), 120))
        label.adjustSize()

    def _show_dialog(self, text: str):
        """显示对话框文本"""
        anchor = self._pet_anchor()
        self.talk_label.setText(text)
        self.talk_label.setStyleSheet(self._bubble_style())
        self._layout_bubble()
        self.talk_label.show()
        self._keep_pet_anchor(anchor)

    def _init_timers(self):
        """初始化定时器"""
        # 对话切换（同一节拍驱动：每 6 秒同时弹出文字气泡与切换表情）
        self.talk_timer = QTimer(self)
        self.talk_timer.timeout.connect(self._update_talk)
        self.talk_timer.timeout.connect(self._update_animation)
        self.talk_timer.start(6000)

        # 休息提醒
        self.rest_timer = QTimer(self)
        self.rest_timer.timeout.connect(self._show_rest_reminder)
        
        # 待办提醒定时器（每分钟检查一次）
        self.todo_timer = QTimer(self)
        self.todo_timer.timeout.connect(self._check_todo_reminder)
        self.todo_timer.start(60000)  # 每分钟检查
        self._check_todo_reminder()  # 启动时检查一次

        # 计时器刷新（每秒跳动）
        self.timer_tick = QTimer(self)
        self.timer_tick.timeout.connect(self._update_timer_display)

    # ---------------- 计时模块 ----------------

    def _timer_label_style(self) -> str:
        """计时器标签样式（等宽字体，字号可在设置中调整）"""
        return f"""
            QLabel {{
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: {self._timer_font_pt}pt;
                font-weight: bold;
                color: {TEXT_ON_PRIMARY};
                background-color: {PIKACHU_YELLOW};
                border: 2px solid {PIKACHU_YELLOW_EDGE};
                border-radius: 12px;
                padding: 2px 14px;
            }}
        """

    def _toggle_timer(self):
        """点击宠物：开始 / 结束计时"""
        if self._timer_running:
            self._stop_timer()
        else:
            self._start_timer()

    def _start_timer(self):
        """开始计时"""
        anchor = self._pet_anchor()  # 先记下皮卡丘当前位置

        self._timer_running = True
        self._timer_start_dt = datetime.now()
        self._timer_start_mono = time.monotonic()

        self.timer_label.setText("⏱ 00:00")
        self.timer_label.show()
        self.timer_tick.start(1000)

        self._show_state(self.STATE_IDLE)
        self._show_dialog("⏱ 计时开始，再点我一下结束")
        # 24pt 计时器 + 长气泡会把窗口撑大，这里补偿位移让皮卡丘原地不动
        self._keep_pet_anchor(anchor)
        log.info("开始计时")

    def _stop_timer(self):
        """结束计时：记录本次时长并提示（过短视为误触取消，不落盘）"""
        if not self._timer_running:
            return

        anchor = self._pet_anchor()  # 收起前先记下位置
        elapsed = self._elapsed_seconds()
        self._timer_running = False
        self.timer_tick.stop()
        self.timer_label.hide()

        # 不到 2 秒当成误触，按「取消」处理，不写记录
        if elapsed < 2:
            self._show_dialog("⏹ 已取消计时（时间太短，未记录）")
            log.info(f"取消计时: {elapsed}s")
            self._timer_start_dt = None
            self._timer_start_mono = None
            self._keep_pet_anchor(anchor)
            return

        try:
            TimerStorage.append_record(self._timer_start_dt, elapsed)
        except Exception as exc:  # 记录失败不该影响使用
            log.warning(f"计时记录写入失败: {exc}")

        total = TimerStorage.today_total_seconds()
        self._show_dialog(
            f"⏹ 本次 {TimerStorage.format_duration(elapsed)}"
            f"（今日累计 {TimerStorage.format_duration(total)}）"
        )
        log.info(f"结束计时: {elapsed}s")

        self._timer_start_dt = None
        self._timer_start_mono = None
        self._keep_pet_anchor(anchor)

    def _elapsed_seconds(self) -> int:
        """已计时秒数"""
        if self._timer_start_mono is None:
            return 0
        return int(time.monotonic() - self._timer_start_mono)

    def _pet_anchor(self):
        """宠物图像左上角在屏幕上的坐标"""
        label = getattr(self, "image_label", None)
        if label is None:
            return (self.x(), self.y())
        return (self.x() + label.x(), self.y() + label.y())

    def _keep_pet_anchor(self, anchor, retry: bool = True):
        """窗口尺寸变化后，把皮卡丘挪回 anchor 位置

        24pt 计时器和长气泡都会把窗口撑得比宠物宽，Qt 默认以左上角为
        基准缩放，宠物就会跟着跑位。这里统一按宠物锚点反向补偿。
        """
        self.adjustSize()
        if self.layout() is not None:
            self.layout().activate()

        cur = self._pet_anchor()
        dx, dy = cur[0] - anchor[0], cur[1] - anchor[1]
        if dx or dy:
            nx, ny = self.x() - dx, self.y() - dy
            screen = QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                nx = max(area.left(), min(nx, area.right() - self.width() + 1))
                ny = max(area.top(), min(ny, area.bottom() - self.height() + 1))
            self.move(nx, ny)

        if retry:
            # 部分窗口管理器下尺寸变化是异步的，下一拍再校正一次
            QTimer.singleShot(0, lambda: self._keep_pet_anchor(anchor, False))

    def _update_timer_display(self):
        """刷新计时器显示"""
        if not self._timer_running:
            return
        self.timer_label.setText(f"⏱ {TimerStorage.format_clock(self._elapsed_seconds())}")

    def _random_position(self):
        """随机位置"""
        screen = QApplication.primaryScreen().geometry()
        x = int(random.random() * (screen.width() - self.width()))
        y = int(random.random() * (screen.height() - self.height()))
        self.move(x, y)

    def _update_talk(self):
        """更新对话气泡（表情变化由 _update_animation 定时轮换）"""
        if self._current_state == self.STATE_IDLE and self.idle_dialogs:
            text = random.choice(self.idle_dialogs)
            anchor = self._pet_anchor()
            self.talk_label.setText(text)
            self.talk_label.setStyleSheet(self._bubble_style())
            self._layout_bubble()
            self.talk_label.show()
            self._keep_pet_anchor(anchor)

    # 自动轮换的表情动作（按 manifest 里实际存在的动态筛选）
    AUTO_EXPRESSIONS = ["blink", "happy", "tilt", "sway", "hop", "cheer", "laugh", "shy"]

    def _available_expressions(self):
        """动作包里可用的自动表情列表"""
        if not self._actions:
            return []
        return [a for a in self.AUTO_EXPRESSIONS if a in self._actions]

    def _update_animation(self):
        """定时换表情：每隔几秒随机播一个表情，其余时间保持待机呼吸"""
        if self._current_state != self.STATE_IDLE:
            return
        exprs = self._available_expressions()
        if not exprs or random.random() > 0.6:
            # 40% 概率回到呼吸待机
            self._play_animation(self._get_idle_animation())
            return
        pick = random.choice(exprs)
        info = self._actions.get(pick, {})
        if info.get("loop", True):
            # 循环类表情限时播放（跳跃/害羞等），播几秒回待机（GIF 总长约 3.4s，不能低于它）
            self._play_action(pick, auto_revert_ms=random.choice([3500, 4200, 5000]))
        else:
            self._play_action(pick)

    def _show_rest_reminder(self):
        """显示休息提醒"""
        self._current_state = self.STATE_REST
        self._show_state(self.STATE_REST)
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )

        # 播放提醒提示音
        sound_manager.play_reminder()

        # 使用配置的提醒内容
        messages = self._rest_config.get("message", "")
        if messages:
            rest_dialog = messages
        else:
            rest_dialog = self.states.get(self.STATE_REST, {}).get("dialog", "⏰ 该休息啦！")

        # 显示对话框
        self._show_dialog(rest_dialog)

    def refresh_todo_config(self):
        """刷新待办配置（从文件重新加载）"""
        todo_enabled = self.config.get("todo_reminder", {}).get("enabled", True)
        self._todo_config = {
            "enabled": todo_enabled,
            "todos": TodoStorage.load_todos(),
        }
        # 更新系统上下文中的待办事项
        self.persona_manager.update_project_context(todos=self._todo_config.get("todos", []))

    def _check_todo_reminder(self):
        """检查待办事项是否到提醒时间"""
        from datetime import datetime
        
        if not self._todo_config.get("enabled", True):
            return

        todos = self._todo_config.get("todos", [])
        if not todos:
            return
        
        current_time = datetime.now().strftime("%H:%M")
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        for todo in todos:
            if todo.get("done", False):
                continue  # 跳过已完成的
            
            todo_time = todo.get("time", "")
            todo_content = todo.get("content", "")
            
            # 检查是否到达提醒时间
            if todo_time == current_time:
                # 检查今天是否已经提醒过
                check_key = f"{current_date}_{todo_content}_{todo_time}"
                if check_key not in self._last_todo_check:
                    self._show_todo_reminder(todo_content, todo_time)
                    self._last_todo_check[check_key] = True

    def _show_todo_reminder(self, content: str, time: str):
        """显示待办提醒"""
        self._current_state = self.STATE_REST

        # 只播放休息状态的动画，不显示其对话框
        state_config = self.states.get(self.STATE_REST, DEFAULT_STATES.get(self.STATE_REST, {}))
        anim_path = state_config.get("animation", "")
        if anim_path:
            self._play_animation(anim_path)

        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )

        # 播放待办提醒提示音
        sound_manager.play_reminder()

        # 显示待办提醒
        todo_dialog = f"📝 待办提醒: {content} @ {time}"
        self._show_dialog(todo_dialog)

    def _reset_to_idle(self):
        """重置为待机状态"""
        self._current_state = self.STATE_IDLE
        if self.idle_animations:
            self._play_animation(random.choice(self.idle_animations))
        if self.talk_label.isVisible():
            anchor = self._pet_anchor()
            self.talk_label.hide()
            self._keep_pet_anchor(anchor)

    def mousePressEvent(self, event):
        """鼠标按下：记录位置，准备判断「点击」还是「拖拽」"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.pos()
            self._press_global = event.globalPos()
            self._press_moved = False
            self._cancel_action_revert()
            self._current_state = self.STATE_CLICK
            self._show_state(self.STATE_CLICK)
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动（拖拽）"""
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            # 位移超过阈值就认定是拖拽，松开时不再触发计时
            if self._press_global is not None:
                if (event.globalPos() - self._press_global).manhattanLength() > 5:
                    self._press_moved = True
            # 拖拽状态
            if self._current_state != self.STATE_DRAG:
                self._current_state = self.STATE_DRAG
                self._show_state(self.STATE_DRAG)
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放：几乎没位移视为点击 -> 切换计时"""
        is_click = (
            event.button() == Qt.LeftButton
            and not self._press_moved
            and self._drag_pos is not None
        )
        self._drag_pos = None
        self._press_global = None
        self._reset_to_idle()
        if is_click:
            self._toggle_timer()

    def enterEvent(self, event):
        """鼠标进入"""
        self.setCursor(QCursor(Qt.ClosedHandCursor))

    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: white;
                border: 1px solid {PIKACHU_YELLOW};
                border-radius: 6px;
                padding: 4px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 24px;
                border-radius: 4px;
                color: #333;
                background-color: transparent;
            }}
            QMenu::item:selected {{
                background-color: {PIKACHU_YELLOW};
                color: {TEXT_ON_PRIMARY};
            }}
            QMenu::item:disabled {{
                color: #999;
            }}
        """)

        hide_action = menu.addAction("隐藏")
        chat_action = menu.addAction(f"与 {self.persona_manager.name} 聊天")
        timer_text = "⏹ 结束计时" if self._timer_running else "⏱ 开始计时"
        timer_action = menu.addAction(timer_text)

        # 表情 / 动作子菜单（动作包驱动；可手动指定表情，回到待机恢复呼吸动画）
        action_menu = menu.addMenu("表情 / 动作")
        back_action = action_menu.addAction("回到待机")
        back_action.triggered.connect(self._reset_to_idle)
        action_menu.addSeparator()
        if self._actions:
            for act_id, info in self._actions.items():
                act = action_menu.addAction(info.get("name", act_id))
                act.triggered.connect(
                    lambda checked=False, aid=act_id: self._play_action(aid)
                )
        else:
            disabled = action_menu.addAction("（无可用动作）")
            disabled.setEnabled(False)

        font_action = menu.addAction("字号设置")
        today_total = TimerStorage.today_total_seconds()
        if today_total:
            total_action = menu.addAction(f"今日累计 {TimerStorage.format_duration(today_total)}")
            total_action.setEnabled(False)
        rest_text = "关闭休息提醒" if self._rest_enabled else "打开休息提醒"
        rest_action = menu.addAction(rest_text)
        menu.addSeparator()
        quit_action = menu.addAction("退出")

        action = menu.exec_(self.mapToGlobal(event.pos()))

        if action == quit_action:
            self._quit()
        elif action == hide_action:
            self.setWindowOpacity(0)
        elif action == chat_action:
            self._open_chat()
        elif action == timer_action:
            self._toggle_timer()
        elif action == font_action:
            self._open_font_settings()
        elif action == rest_action:
            self._rest_enabled = not self._rest_enabled
            # 同步更新配置文件
            self.config.setdefault("rest_reminder", {})
            self.config["rest_reminder"]["enabled"] = self._rest_enabled
            ConfigLoader.save(self.config)
            if self._rest_enabled:
                # 使用配置的间隔（毫秒）
                interval_ms = self._rest_config.get("interval", 3600) * 1000
                self.rest_timer.start(interval_ms)
            else:
                self.rest_timer.stop()

    def update_all_ui(self):
        """更新所有UI（人设名称变化时调用）"""
        # 更新宠物尺寸
        new_size = self.config.get("ui", {}).get("pet_size", 100)
        if new_size != self._pet_size:
            self._pet_size = new_size
            # 重新播放动画以应用新尺寸
            if self.idle_animations:
                self._play_animation(random.choice(self.idle_animations))
            # 重新调整窗口大小
            self.adjustSize()
        # 更新聊天窗口
        if self._chat_window:
            self._chat_window.update_persona_name(self.persona_manager.name)

    def _open_font_settings(self):
        """打开字号设置对话框"""
        from ui.font_dialog import FontSizeDialog

        dialog = FontSizeDialog(self.config, self)
        if dialog.exec_() == QDialog.Accepted:
            self._apply_font_settings()

    def _apply_font_settings(self):
        """字号设置保存后：重读配置并刷新所有文字样式"""
        self.config = ConfigLoader.load()
        ui_conf = self.config.get("ui", {})
        timer_pt = int(ui_conf.get("display_font_pt", TIMER_FONT_PT))
        chat_pt = int(ui_conf.get("chat_font_pt", BUBBLE_FONT_PT))
        if timer_pt == self._timer_font_pt and chat_pt == self._chat_font_pt:
            return

        self._timer_font_pt = timer_pt
        self._chat_font_pt = chat_pt
        log.info(f"应用字号设置: 显示={timer_pt}pt, 对话={chat_pt}pt")

        # 计时器样式即时刷新（显示中就带锚点补偿，避免窗口变化导致跑位）
        timer_visible = self.timer_label.isVisible()
        anchor = self._pet_anchor()
        self.timer_label.setStyleSheet(self._timer_label_style())
        # 气泡样式即时刷新（隐藏中则下次显示时自然生效）
        self.talk_label.setStyleSheet(self._bubble_style())
        if timer_visible:
            self._layout_bubble()
            self._keep_pet_anchor(anchor)
        else:
            self._keep_pet_anchor(anchor)

        # 聊天窗口在打开时读取字号，这里关掉让下次打开用新字号
        if self._chat_window is not None:
            self._chat_window.close()
            self._chat_window = None

    def _show_window(self):
        """显示窗口"""
        self.setWindowOpacity(1)
        self.show()

    def _open_chat(self):
        """打开聊天窗口"""
        # 每次打开重新创建窗口以应用最新配置
        if self._chat_window is not None:
            self._chat_window.close()
        self._chat_window = ChatWindow(
            self.config,
            self.chat_service,
            self.memory_manager,
            self.persona_manager,
            None,
            self,  # 传入 pet 引用
        )
        self._chat_window.settings_requested.connect(self._open_settings)
        self._chat_window.show()
        self._chat_window.raise_()

    def _open_settings(self):
        """打开设置"""
        dialog = SettingsDialog(self.config, self._chat_window)
        self._settings_dialog = dialog  # 保存引用以便刷新
        if dialog.exec_():
            self.chat_service.update_config(self.config)
            # 重新加载状态配置
            self._load_states_config()
            self._load_idle_resources()
            # 更新所有UI
            self.update_all_ui()
            # 同步更新休息提醒状态
            self._sync_rest_reminder_state()

        self._settings_dialog = None  # 对话框关闭后清除引用

    def _sync_rest_reminder_state(self):
        """同步休息提醒状态（从配置更新到内存和定时器）"""
        rest_config = self.config.get("rest_reminder", {})
        new_enabled = rest_config.get("enabled", False)

        # 如果状态发生变化
        if new_enabled != self._rest_enabled:
            self._rest_enabled = new_enabled
            self._rest_config = rest_config

            if new_enabled:
                interval_ms = rest_config.get("interval", 3600) * 1000
                self.rest_timer.start(interval_ms)
            else:
                self.rest_timer.stop()
        else:
            # 状态没变，但间隔可能变了
            if new_enabled:
                new_interval = rest_config.get("interval", 3600) * 1000
                current_interval = self._rest_config.get("interval", 3600) * 1000
                if new_interval != current_interval:
                    self.rest_timer.setInterval(new_interval)
            self._rest_config = rest_config

    def _quit(self):
        """退出程序"""
        # 先隐藏聊天窗口
        if self._chat_window is not None:
            self._chat_window.hide()
        self.memory_manager.save_to_file()
        messages = self.memory_manager.get_messages()
        if len(messages) >= 4:
            self._do_analyze_and_quit()
        else:
            ConfigLoader.save(self.config)
            QApplication.quit()

    def _do_analyze_and_quit(self):
        """分析用户画像并退出"""
        self.talk_label.setText("正在分析用户画像...")
        self.talk_label.show()
        QApplication.processEvents()

        messages = self.memory_manager.get_messages()
        api_config = self.config.get("api", {})
        worker = ProfileAnalyzeWorker(self.persona_manager, messages, api_config)
        worker.finished.connect(self._on_analyze_done)
        # 延迟执行，让用户先看到提示
        QTimer.singleShot(1500, lambda: (self.hide(), worker.run()))

    def _on_analyze_done(self, profile: dict):
        """分析完成"""
        if profile:
            for dim_key, value in profile.items():
                if value:
                    self.persona_manager.update_user_profile(dim_key, value)
        ConfigLoader.save(self.config)
        QApplication.quit()


def main():
    """主入口"""
    # 初始化日志系统
    init_logging()
    log.info("桌面宠物应用启动")
    
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    log.info("桌面宠物窗口已显示")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()