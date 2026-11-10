"""
Django settings，个人网站项目。

设计原则：
- 环境差异全部走 .env；未做任何配置时，本地 SQLite 即可零配置启动。
- 只有一个 admin 用户，登录统一走 Django admin 的登录页。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 路径与 .env 加载
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# override=True：本地修改 .env 后无需清理环境变量即可生效
load_dotenv(BASE_DIR / ".env", override=True)


def env_bool(name: str, default: str = "false") -> bool:
    """宽松的布尔环境变量解析：1/true/yes/on 均视为 True。"""
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list:
    """逗号分隔的环境变量 → list。"""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# 基础安全配置
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    # 本地开发兜底值；生产必须显式配置 DJANGO_SECRET_KEY
    "django-insecure-dev-only-key-DO-NOT-USE-IN-PRODUCTION",
)

DEBUG = env_bool("DJANGO_DEBUG", "true")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# 生产 HTTPS 站点需要，例如 https://example.com
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 本站应用
    "blog.apps.BlogConfig",
    "chat.apps.ChatConfig",
    "ledger.apps.LedgerConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            # 模板内置标签：子模板里可直接用 {% static %} 不必重复 {% load static %}
            "builtins": ["django.templatetags.static"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# 数据库：未配置时默认 SQLite，本地零配置可跑；生产 .env 里切 MySQL
# ---------------------------------------------------------------------------
_db_engine = os.getenv("DB_ENGINE", "sqlite").strip().lower()

if _db_engine in ("mysql", "mariadb"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "personal_site"),
            "USER": os.getenv("DB_USER", "site"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "db"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {
                "charset": "utf8mb4",
                # MySQL 8 严格模式，避免脏数据静默截断
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    _sqlite_path = BASE_DIR / "data" / "db.sqlite3"
    # 本地零配置：目录不存在则自动创建（Docker/生产用 MySQL 不走这里）
    _sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _sqlite_path,
        }
    }

# ---------------------------------------------------------------------------
# 用户与密码校验
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# 国际化
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# 静态文件与媒体文件
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
# 开发时 Django 从这里找 CSS/JS/vendor
STATICFILES_DIRS = [BASE_DIR / "static"]
# collectstatic 收集目标：生产由 nginx 直接服务该目录（挂载为卷）
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# 用户上传图片校验（blog 模块）
BLOG_IMAGE_MAX_BYTES = int(os.getenv("BLOG_IMAGE_MAX_BYTES", str(10 * 1024 * 1024)))

# ---------------------------------------------------------------------------
# 聊天模块 LLM 配置（OpenAI 兼容接口，默认智谱 GLM）
# ---------------------------------------------------------------------------
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-5.3")

# ---------------------------------------------------------------------------
# 其他
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 未登录访问需登录页面时跳转到 Django admin 登录页（全站唯一账号）
LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# 容器/反代环境：信任 X-Forwarded-Proto 判断 https
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
}
