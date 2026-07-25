import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    ALAS_UPSTREAM = os.environ.get("ALAS_UPSTREAM", "http://127.0.0.1:22267").rstrip("/")
    USER_DATA_PATH = os.environ.get(
        "USER_DATA_PATH",
        str(_ROOT / "dap_data" / "UserData.json"),
    )
    # ProAlas 运行截图目录；默认 UserData 同级 img/（即 data/img/{device_id}/）
    DEVICE_SCREENSHOT_ROOT = os.environ.get("DEVICE_SCREENSHOT_ROOT", "").strip()
    # 嵌入 Github_Open_Proalas 时默认读本仓库 config/
    CONFIG_DIR = os.environ.get(
        "CONFIG_DIR",
        str(_ROOT / "config"),
    )
    TIMETABLE_PATH = os.environ.get("TIMETABLE_PATH", "").strip()
    HOST_CONTROL_PATH = os.environ.get("HOST_CONTROL_PATH", "").strip()
    MMC_COMMAND_URL = os.environ.get("MMC_COMMAND_URL", "").strip().rstrip("/")
    MMC_COMMAND_TOKEN = os.environ.get("MMC_COMMAND_TOKEN", "").strip()
    # 临时远控（py-scrcpy）：按套餐配额（秒）
    # Normal 默认日 10 分钟 / 单次 10 分钟；Pro 日 2 小时 / 单次最长 60 分钟
    REMOTE_DAILY_QUOTA_NORMAL_SEC = int(os.environ.get("REMOTE_DAILY_QUOTA_NORMAL_SEC", "600"))
    REMOTE_DAILY_QUOTA_PRO_SEC = int(os.environ.get("REMOTE_DAILY_QUOTA_PRO_SEC", "7200"))
    REMOTE_SESSION_TTL_NORMAL_SEC = int(os.environ.get("REMOTE_SESSION_TTL_NORMAL_SEC", "600"))
    REMOTE_SESSION_TTL_PRO_SEC = int(os.environ.get("REMOTE_SESSION_TTL_PRO_SEC", "3600"))
    # 兼容旧变量名（仅作 Normal 回退，见 remote_control）
    REMOTE_SESSION_TTL_SEC = int(os.environ.get("REMOTE_SESSION_TTL_SEC", "600"))
    REMOTE_DAILY_QUOTA_SEC = int(os.environ.get("REMOTE_DAILY_QUOTA_SEC", "600"))
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH",
        str(_ROOT / "dap_data" / "proalas.db"),
    )
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # OpenAI 兼容对话（密钥勿写入仓库，用环境变量）
    OPENAI_API_KEY = (os.environ.get("OPENAI_API_KEY") or "").strip()
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    PRE_PROMPT_PATH = os.environ.get(
        "PRE_PROMPT_PATH",
        str(_ROOT / "dap_commands" / "预提示词.txt"),
    )
    # 每设备 chat.jsonl、commands.json 根目录（Docker 建议挂到 /data/commands）
    COMMANDS_DIR = os.environ.get("COMMANDS_DIR", str(_ROOT / "dap_commands"))
    AI_DAILY_QUESTION_LIMIT = int(os.environ.get("AI_DAILY_QUESTION_LIMIT", "50"))
    AI_MAX_MESSAGE_LEN = int(os.environ.get("AI_MAX_MESSAGE_LEN", "1000"))
    ANNOUNCEMENT_PATH = os.environ.get(
        "ANNOUNCEMENT_PATH",
        str(_ROOT / "dap_data" / "更新公告.md"),
    )
