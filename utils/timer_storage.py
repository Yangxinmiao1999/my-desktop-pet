"""计时记录存储工具

每次计时结束后把记录追加到 data/timers.json，方便回顾一天里专注了多久。
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class TimerStorage:
    """计时记录存储类"""

    DATA_FILE = os.path.join("data", "timers.json")
    MAX_RECORDS = 500  # 只保留最近 500 条，避免文件无限增长

    @classmethod
    def load_records(cls) -> List[Dict[str, Any]]:
        """加载全部计时记录"""
        if not os.path.exists(cls.DATA_FILE):
            return []
        try:
            with open(cls.DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    @classmethod
    def append_record(
        cls, start: datetime, seconds: int, label: str = ""
    ) -> Dict[str, Any]:
        """追加一条计时记录并落盘"""
        end = datetime.now()
        record = {
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "seconds": int(seconds),
            "duration": cls.format_duration(seconds),
            "label": label,
        }
        records = cls.load_records()
        records.append(record)
        records = records[-cls.MAX_RECORDS :]
        cls._save(records)
        return record

    @classmethod
    def today_records(cls) -> List[Dict[str, Any]]:
        """取今天的记录"""
        today = datetime.now().strftime("%Y-%m-%d")
        return [r for r in cls.load_records() if str(r.get("start", "")).startswith(today)]

    @classmethod
    def today_total_seconds(cls) -> int:
        """今天累计计时秒数"""
        return sum(int(r.get("seconds", 0)) for r in cls.today_records())

    @classmethod
    def _save(cls, records: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(cls.DATA_FILE) or ".", exist_ok=True)
        with open(cls.DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    @staticmethod
    def format_duration(seconds: int) -> str:
        """把秒数转成人话：45 秒 / 12 分 30 秒 / 1 小时 5 分"""
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours} 小时 {minutes} 分" if minutes else f"{hours} 小时"
        if minutes:
            return f"{minutes} 分 {secs} 秒" if secs else f"{minutes} 分"
        return f"{secs} 秒"

    @staticmethod
    def format_clock(seconds: int) -> str:
        """秒表显示格式：05:23 / 1:05:23"""
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
