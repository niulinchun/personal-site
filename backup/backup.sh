#!/usr/bin/env bash
# ============================================================
# 个人网站备份：MySQL 数据 + media 上传图片
# - 数据库：docker exec mysqldump | gzip
# - media ：tar 打包 web 容器内的 /app/media
# - 保留最近 N 份，默认 7 份
# 用法：
#   bash backup/backup.sh                 # 默认保留 7 份
#   KEEP=14 bash backup/backup.sh        # 保留 14 份
# crontab 示例（每天 04:00）：
#   0 4 * * * cd /opt/personal-site && bash backup/backup.sh >> backup/backup.log 2>&1
# ============================================================
set -euo pipefail

# 进入项目根目录（backup/ 的上一级）
cd "$(dirname "$0")/.."

# 读取 .env（DB_NAME / DB_USER / DB_PASSWORD），compose 也在用同一份
set -a
# shellcheck disable=SC1091
[ -f .env ] && source .env
set +a

DOMAIN_NAME="${DOMAIN:-site}"
BACKUP_DIR="${BACKUP_DIR:-backup/files}"
KEEP="${KEEP:-7}"
STAMP="$(date +%Y%m%d-%H%M%S)"

DB_NAME="${DB_NAME:-personal_site}"
DB_USER="${DB_USER:-site}"
: "${DB_PASSWORD:?请在 .env 中配置 DB_PASSWORD}"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%F %T')] 开始备份：Domain=$DOMAIN_NAME Keep=$KEEP"

# ---------------------------------------------------------- 1) MySQL
echo "[$(date '+%F %T')] 导出数据库 $DB_NAME ..."
docker compose exec -T db sh -c \
  "exec mysqldump --default-character-set=utf8mb4 --single-transaction \
     -u'${DB_USER}' -p'${DB_PASSWORD}' '${DB_NAME}'" \
  | gzip > "${BACKUP_DIR}/db-${STAMP}.sql.gz"
echo "[$(date '+%F %T')] 数据库导出完成：$(du -h "${BACKUP_DIR}/db-${STAMP}.sql.gz" | cut -f1)"

# ---------------------------------------------------------- 2) media
echo "[$(date '+%F %T')] 打包 media ..."

docker compose exec -T web tar czf - -C /app media \
  > "${BACKUP_DIR}/media-${STAMP}.tar.gz"
echo "[$(date '+%F %T')] media 打包完成：$(du -h "${BACKUP_DIR}/media-${STAMP}.tar.gz" | cut -f1)"

# ---------------------------------------------------------- 3) 清理旧备份
ls -1t "${BACKUP_DIR}"/db-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f --
ls -1t "${BACKUP_DIR}"/media-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f --

echo "[$(date '+%F %T')] 备份完成。"
