# 个人小站（Django 4.2 + Bootstrap5 + GLM + 记账）

纯个人网站，单管理员账号，无注册。三个子模块：

| 模块 | 前缀 | 说明 |
| --- | --- | --- |
| 博客 | `/blog/` | 三栏知识库布局，Markdown 文章 + 分类 + 评论 + 图片粘贴上传（前台公开可读） |
| GLM 问答 | `/chat/` | OpenAI 兼容接口接入 GLM，SSE 流式逐字返回（整模块需登录） |
| 记账 | `/ledger/` | 月份流水 + 汇总卡片 + Chart.js 报表（整模块需登录） |
| 后台 | `/admin/` | Django admin：分类/评论删除/记账分类维护等 |

URL 前缀括约：`/blog/` `/chat/` `/ledger/` `/admin/`，媒体 `/media/`，静态 `/static/`。

```
personal-site/
├── manage.py
├── config/                 # settings / urls / asgi / wsgi / PyMySQL 注册
├── blog/                   # 博客 app（含 cleanup_images、import_backup_sql、import_old_blog 命令）
├── chat/                   # GLM 问答 app（httpx 流式 + SSE）
├── ledger/                 # 记账 app
├── templates/              # base / blog / chat / ledger / login
├── static/                 # css + js + vendor（Bootstrap/Chart.js/marked 本地化）
├── nginx/nginx.conf.template   # 生产 nginx 模板（${DOMAIN} 注入）
├── backup/backup.sh            # mysqldump + media 打包
├── Dockerfile / docker-compose.yml
├── requirements.txt / .env.example
└── README.md
```

---

## 一、本地开发（Windows + Python 3.8 + SQLite）

本地 **零配置** 即可运行：不配 `DB_*` 时默认 SQLite（`data/db.sqlite3`），不需要 MySQL。

```powershell
# 1) 取代码，建虚拟环境（本机 3.8；生产镜像为 python:3.12，语法向下兼容）
cd D:\workspace\python_projects\personal-site
py -3.8 -m venv .venv
.\.venv\Scripts\Activate.ps1
# 若 PowerShell 报执行策略错误：
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2) 装依赖（国内网络可加：-i https://pypi.tuna.tsinghua.edu.cn/simple）
pip install -r requirements.txt

# 3) 环境变量（可选）：cp .env.example .env
#    本地 SQLite 默认可跑；想用 GLM 问答要填 LLM_API_KEY

# 4) 初始化
python manage.py migrate
python manage.py createsuperuser    # 唯一账号，全站管理用

# 5) 启动
python manage.py runserver
```

访问：

| 页面 | 地址 |
| --- | --- |
| 博客前台 | <http://127.0.0.1:8000/blog/> |
| 文章管理 | <http://127.0.0.1:8000/blog/manage/>（登录后） |
| GLM 问答 | <http://127.0.0.1:8000/chat/>（登录后，需 LLM_API_KEY） |
| 记账 | <http://127.0.0.1:8000/ledger/>（登录后） |
| 报表 | <http://127.0.0.1:8000/ledger/report/> |
| 后台 | <http://127.0.0.1:8000/admin/> |

顺手自检（含登录范围 / SSE / 记账汇总 / 文章图片归属等测试）：

```powershell
python manage.py test
```

### 本地首次推送到 GitHub（已做前半，剩余命令对照执行）

仓库已在本地初始化并以 `niulinchun` 身份首次提交（74 文件）：

```powershell
cd D:\workspace\python_projects\personal-site
git init -b main
git config user.name "niulinchun"
git config user.email "18041033@qq.com"
git add -A
git commit -m "init: personal site (blog/chat/ledger + Docker deploy)"
```

`.gitattributes` 已强制 LF（防 `.sh`/Dockerfile 在 Linux 变 CRLF 跑不起来）；
`.gitignore` 已排除 `.env`、`.venv/`、`data/`、`media/`、`backup*.sql` 等本地产物。

剩余你要做的（先在 <https://github.com/new> 建 **私有空仓库** `personal-site`，不要勾选 README 初始化）：

```powershell
git remote add origin git@github.com:niulinchun/personal-site.git
git push -u origin main
```

> push 走 SSH 需要本机有 GitHub 密钥：`ssh-keygen -t ed25519 -N "" -f $HOME\.ssh\id_ed25519`，
> 然后把 `C:\Users\<你>\.ssh\id_ed25519.pub` 内容贴到 GitHub → Settings → SSH and GPG keys → New SSH key。
> 若本机连 github.com 不稳，可临时改推 HTTPS 并用 Personal Access Token 当密码；
> 或按第三节用 Gitee 做跳板备选。

日常提交（`-u` 只需首次推 main 时带一次）：

```powershell
git add -A
git commit -m "改动说明"
git push
```

### 排错：push 失败的四道关卡（本次实测全踩过一遍）

| # | 报错/现象 | 原因 | 解法 |
| --- | --- | --- | --- |
| 1 | `banner exchange: ... Connection refused` | 直连 `github.com:22` 被网络拦截（家宽/校园网常见） | 在 `%USERPROFILE%\.ssh\config` 加一段，把 GitHub SSH 改走 443：`Host github.com` / `HostName ssh.github.com` / `Port 443` / `User git`；首次连接报 `Host key verification failed` 就带 `-o StrictHostKeyChecking=accept-new` 预接受一次 |
| 2 | `Permission denied (publickey)` | 本机公钥没加到 GitHub 账号 | 用 `Get-Content $HOME\.ssh\id_ed25519.pub` 打出公钥全文，贴到 GitHub → Settings → SSH and GPG keys → New SSH key |
| 3 | `ERROR: Repository not found.` | 远端仓库没建，或用户名/仓库名写错 | <https://github.com/new> 建仓（名称与 remote URL 一字不差）；名字不一致就 `git remote set-url origin git@github.com:实际用户/实际仓.git` |
| 4 | `! [rejected] (fetch first)` + `Updates were rejected` | 建仓时勾了 Add a README/.gitignore/license 初始化，远端已有提交挡住了首次 push | 按"安全的 force 覆盖流程"处理（见下） |

验证身份与通道：

```powershell
ssh -T git@github.com    # 通的标志：Hi <用户名>! You've successfully authenticated...
```

### force push：怎么用才是安全的

`--force` 会**直接把远端分支指针改成与本地一致，丢弃远端多余的历史**。所以它只适合"远端只有建仓生成的空模板"这类场景（本次就是勾了 README 初始化产生的 `Initial commit`），**绝不能**对有真实工作的远端使用。

安全的 force 覆盖流程（先看后删，再覆盖）：

```powershell
git fetch origin                            # ① 先拉取远端引用（不动本地分支）
git log --oneline origin/main -5            # ② 看远端多了哪些提交
git ls-tree --name-only -r origin/main      # ③ 看远端有哪些文件
git diff --stat main...origin/main          # ④ 对比本地/远端差异
# 若 ②③④ 确认远端仅是初始化模板、无你的工作 → 才允许覆盖：
git push -u origin main --force
```

命令拆解：

```powershell
git push -u origin main --force
#       │  │       └-- 不做"远端是本地祖先"检查，直接改写远端分支指针
#       │  └-- 推 main 分支
#       └- 首次推送时同时设置上游（之后裸 git push 即可）
```

> 习惯建议：平时宁可写 `--force-with-lease` 而不是 `--force`——它只在"远端仍停在你本地已知的那个位置"时才覆盖；如果有人/另一台机器刚推过新提交，它会拒绝而不是悄悄抹掉。单人开发时二者等效，前者是更稳的习惯。

---

## 二、导入旧 Java 博客数据

旧数据提供两种导入命令，按你的数据形态二选一：

### 2.1 `import_backup_sql` —— 直接读 mysqldump 文件（推荐，本次实测通过）

旧站的 `backup.sql` 实测结构：

- 只有一张 `article` 表（没有独立 category 表），列为 `article_title / article_category(分类名) / article_content`；
- 三个字段全部是 **Base32（RFC4648）编码的 UTF-8 文本**（如 `JJQXMYI=` → `Java`）；
- 共 239 篇文章 / 31 个分类（Java、Android、C/C++、Linux……），内容是 Markdown。

把 `backup.sql` 放到项目根目录后：

```powershell
# 预览（只统计不写入）
python manage.py import_backup_sql --file backup.sql --dry-run

# 正式导入
python manage.py import_backup_sql --file backup.sql
```

参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--file` | 必填 | mysqldump 文件路径 |
| `--table` | `article` | 文章表名 |
| `--decode` | `base32` | 字段解码：`base32` / `plain`（明文 dump 用 plain） |
| `--input-charset` | `auto` | dump 文件编码，auto 先 utf-8 后 gb18030 |
| `--limit` | 0 | 只导前 N 篇（试跑用） |
| `--dry-run` | 关 | 只统计不写入 |

规则：只迁 **分类 / 标题 / 内容**；`published_at` 取导入时间；`views/likes` 归 0；
同标题 + 同内容幂等跳过，可重复执行。实测结果：`新增 239 篇，跳过 0`（重复执行时 `跳过 239`）。

> 提示：`backup*.sql` 已加入 `.gitignore`，不会被误提交到仓库。

生产 Docker 环境同样适用（代码是 COPY 进镜像的，backup.sql 放项目根即可进容器）：

```bash
docker compose exec web python manage.py import_backup_sql --file backup.sql
```

### 2.2 `import_old_blog` —— 直连旧库的 MySQL（备用，需要能连上数据库）

如果旧数据还在一个**可连接的 MySQL**（不是 dump 文件）里：

```powershell
# 预览（不写入）
python manage.py import_old_blog --dsn mysql://root:密码@127.0.0.1:3306/oldblog --dry-run

# 先小批量试
python manage.py import_old_blog --dsn mysql://root:密码@127.0.0.1:3306/oldblog --limit 20

# 正式
python manage.py import_old_blog --dsn mysql://root:密码@127.0.0.1:3306/oldblog
```

规则同上；表名/字段名默认 `article/title/content/category_id/id/name`，不一致时用参数覆盖：

```powershell
python manage.py import_old_blog --dsn mysql://root:密码@127.0.0.1:3306/oldblog ^
  --article-table blog_article --category-table blog_category ^
  --article-title-col article_title --article-content-col article_text ^
  --article-category-col category_id --category-name-col category_name ^
  --article-date-col addtime
```

生产 Docker 环境导入（连宿主机旧库）：

```bash
docker compose exec web python manage.py import_old_blog \
  --dsn mysql://root:密码@host.docker.internal:3306/oldblog
# Linux 不支持 host.docker.internal 时，可换 --network host 或 --add-host 处理；也可在本地导完上传备份
```

> **本次实测建议**：直接用 2.1 的 `import_backup_sql` 即可，不需要恢复出 MySQL 服务。

---

## 三、RackNerd VPS 部署（Ubuntu + Docker Compose）

### 0) DNS

在域名解析商添加 A 记录：`example.com → VPS_IP`（如果模板里写了 www，也要加 www 记录）。

### 1) 装 Docker

```bash
# 官方脚本（国内镜像阿里云）
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
# 普通慢速可用官方源
# curl -fsSL https://get.docker.com | sh

sudo systemctl enable --now docker
docker compose version   # 确认 compose v2 可用
```

### 2) 配 Git + 取代码

RackNerd 镜像一般自带 git，没有就装：

```bash
git --version || sudo apt update && sudo apt install -y git
git config --global user.name "niulinchun"
git config --global user.email "18041033@qq.com"
git config --global init.defaultBranch main
```

私有仓库拉取推荐给 VPS 配一条 **只读 Deploy Key**（不暴露你自己账号的私钥）：

```bash
ssh-keygen -t ed25519 -C "racknerd" -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
# 把输出整行复制 → GitHub 仓库页 → Settings → Deploy keys → Add deploy key
# Title 填 racknerd，不要勾选 Allow write access（只读足够拉代码）

# 验证（首次会问 Are you sure you want to continue connecting → 输入 yes）：
ssh -T git@github.com
# 成功标志：Hi niulinchun! You've successfully authenticated...

git clone git@github.com:niulinchun/personal-site.git /opt/personal-site
cd /opt/personal-site
```

> **本次实测**：RackNerd 在美国境内，VPS 直连 `github.com:22` 顺畅，
> 不需要本机那套"SSH 走 443"的备用配置（那是国内网络对出站 22 拦截的对策）。
> 本机连不到 VPS 时的备用入口：RackNerd 客户区（client area）→ 服务器面板 → VNC/Console 网页终端。

#### 个人 SSH key vs Deploy key——别再搞混

| | **个人 SSH key** | **Deploy key** |
| --- | --- | --- |
| 添加位置 | Settings → SSH and GPG keys（账号级） | 仓库 → Settings → Deploy keys（仓库级） |
| 作用范围 | 你账号有权限的**所有**仓库 | **只这一个仓库** |
| 默认权限 | 跟随你在该仓库的读写权限 | **只读**；勾 Allow write access 才能推 |
| 典型场景 | 开发机（日常 `git push`） | 服务器拉部署代码 |
| 泄露后果 | 严重，可写你全部仓库 | 轻，仅一个承诺只读的匿名读者 |

一台机器一把钥匙：本机放个人 key，VPS 放 deploy key。同一台服务器要拉多个私有仓库时按仓库分别发，不要把个人 key 复制上去。

#### ssh-keygen 参数拆解

`ssh-keygen` 生成的是一对：公钥（贴出去、登记到 GitHub）、私钥（留在机器上、用于签名应答，绝不出户）。

| 参数 | 含义 |
| --- | --- |
| `-t ed25519` | 密钥算法。Ed25519 现代推荐：短、快、强度高，不用挑位数；`-t rsa -b 4096` 是老教程写法，现在没理由用它 |
| `-C "racknerd"` | 纯注释，拼在公钥末尾，不参与加密，只供人眼辨认钥匙归属。钥匙多的以后这一眼救命，习惯写主机名/用途 |
| `-N ""` | 私钥口令设为空。服务器密钥必须无口令——否则每次 pull 要人工输密码，crontab 无人值守直接瘫痪。代价是拿到私钥文件者即可冒用，靠 `chmod 600` + 目录 700 兜底 |
| `-f ~/.ssh/id_ed25519` | 输出路径（公钥自动加 `.pub`）。用默认文件名还有个福利：ssh 会自动尝试 `~/.ssh/id_ed25519`，无需再配 `IdentityFile` |

验证链路：GitHub 存公钥 → 连接时 GitHub 发随机挑战 → 本机用私钥签名回传 → GitHub 拿存的公钥验签 → `Hi 用户名!`。全程私钥不离开机器。

没有 git 就 scp 传目录备用：`scp -r D:\workspace\python_projects\personal-site\* user@VPS_IP:/opt/personal-site/`

```bash
cp .env.example .env
nano .env
```

`.env` 里 **生产必须改** 的项：

```
DJANGO_SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_DEBUG=false
DOMAIN=example.com
DJANGO_ALLOWED_HOSTS=example.com,web,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com

DB_ENGINE=mysql
DB_HOST=db
DB_NAME=personal_site
DB_USER=site
DB_PASSWORD=<强密码>        # compose 会拿它初始化 MySQL

LLM_API_KEY=<智谱/兼容平台 key>
```

### 3) 启动 db + web（首次构建）

```bash
docker compose up -d --build db web
docker compose logs -f web    # 里有 migrate / collectstatic 输出
```

`web` 容器启动即自动 `migrate` + `collectstatic`。

### 4) 首次 HTTPS 证书（Let's Encrypt，standalone）

```bash
# nginx 尚未启动，80 端口空闲，standalone 方式最省事：
docker compose --profile tls run --rm -p 80:80 certbot certonly --standalone \
  --agree-tos --email you@example.com -d example.com
```

成功后证书在共享卷 `letsencrypt` 里（路径 `live/<DOMAIN>/`，nginx 模板按这个路径引用）。

### 5) 启动 nginx

```bash
docker compose up -d nginx
curl -I https://example.com     # 200/301 即通
```

访问 `https://example.com`：博客前台公开可读，`/chat/`、`/ledger/`、`/admin/` 需登录。

### 6) 建管理员

```bash
docker compose exec web python manage.py createsuperuser
```

> 换 IP / 重签：证书续期方法见第五节；如 80 已被占用可 `docker compose stop nginx` 后再用 standalone。

---

## 四、1GB 内存 VPS 加 2GB Swap（强烈建议）

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab     # 开机自动挂
echo 'vm.swappiness=10'       | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
free -h    # Swap 应显示 2GiB
```

---

## 五、日常运维

### 更新代码上线

```bash
cd /opt/personal-site
git pull
docker compose up -d --build web     # 重建 web 镜像并重启；启动时自动 migrate
# 改代码只需停 nginx？不需要，nginx 只反代不动它
```

若改了模型：本地 `python manage.py makemigrations blog chat ledger` **提交** migration 文件，线上启动时自动迁移。

### 备份（mysqldump + media 打包，保留 N 份）

```bash
bash backup/backup.sh            # 或 KEEP=14 bash backup/backup.sh
```

骨架 crontab（编辑 `sudo crontab -e`）：

```
# 每天 04:00 备份
0 4 * * * cd /opt/personal-site && bash backup/backup.sh >> backup/backup.log 2>&1
# 每周一 03:30 证书检查续期（<30 天才真正申请），完成后 reload nginx
30 3 * * 1 cd /opt/personal-site && docker compose --profile tls run --rm certbot renew --webroot -w /var/www/certbot && docker compose exec -T nginx nginx -s reload
# 每周日 03:00 清理孤儿图片（未挂在任何文章、且上传已超过 7 天）
0 3 * * 0 cd /opt/personal-site && docker compose exec -T web python manage.py cleanup_images --grace-days 7
```

### 恢复

```bash
# 1) 数据库
gunzip -c backup/files/db-<时间戳>.sql.gz | \
  docker compose exec -T db sh -c "exec mysql -u\$MYSQL_USER -p\"\$MYSQL_PASSWORD\" \$MYSQL_DATABASE"

# 2) media 图片
cat backup/files/media-<时间戳>.tar.gz | \
  docker compose exec -T web sh -c "tar xzf - -C /app"
docker compose restart web
```

### 迁移到新 VPS（compose + volume + 备份 = 一键复原）

新机器按第三节装 Docker 并 clone 代码后：

```bash
# 1. copy 旧机 .env 和 backup/files/*.sql.gz / *.tar.gz
# 2. 启 db+web，导入数据
docker compose up -d --build db web
gunzip -c db-最新.sql.gz | docker compose exec -T db sh -c "exec mysql -u\$MYSQL_USER -p\"\$MYSQL_PASSWORD\" \$MYSQL_DATABASE"
cat media-最新.tar.gz | docker compose exec -T web sh -c "tar xzf - -C /app"
# 3. 证书：standalone 重签（DNS 指向新 IP 后）
docker compose --profile tls run --rm -p 80:80 certbot certonly --standalone --agree-tos --email you@example.com -d example.com
# 4. 启 nginx + 建会话账号已有，直接验证
docker compose up -d nginx
```

---

## 六、关键实现备忘

- **渲染栈**：Bootstrap5 / Chart.js / marked.js 全部在 `static/vendor/` 本地文件，无 CDN。
- **ASGI + uvicorn**：生产 `uvicorn config.asgi:application`，SSE 逐字流式；
  nginx 对 `/chat/api/.../messages/stream/` 配置 `proxy_buffering off; proxy_read_timeout 300s;`
  （`nginx.conf.template`），浏览器端用 fetch + reader 手动解析。
- **MySQL 驱动**：PyMySQL（`config/__init__.py` 里 `install_as_MySQLdb()`），
  Docker 构建免编译；本地默认 SQLite 零配置。
- **图片存储**：`media/uploads/YYYY/MM/<uuid>.<ext>`（`ImageField` 上传）。
  文章保存时按正文里的 `…/media/uploads/…` 地址，把 `Image.post` 关联到对应文章；
  正文不再引用只置空不删文件（防“剪切到别篇文章”误删），
  真正清理走 `cleanup_images`（如实删除时 cascade 到 signal 删除物理文件），
  保留期默认 7 天。CRUD 删除文章时，其 Image 记录级联删除并清文件。
- **SSE 关键**：上游 `LLM_BASE_URL/LLM_MODEL/LLM_API_KEY` 全走 `.env`，
  默认智谱 `https://open.bigmodel.cn/api/paas/v4/` + `glm-5.3`。
  以后换模型改 `.env` 即可，无需改代码。
- **登录控制**：`/blog/` 前台与详情/评论 **公开**；`/blog/manage/**`、`/blog/api/upload/`、
  `/chat/**`、`/ledger/**` 均 `@login_required`（跳 `/admin/login/`）。
- **移动端**：博客 <768px 单栏降级（列表 → 详情整页跳转）；聊天会话列表抽屉。

## 七、排错速查

| 现象 | 处理 |
| --- | --- |
| `DisallowedHost` | `.env` 的 `DJANGO_ALLOWED_HOSTS` 少了你的域名或 `web` |
| 403 `CSRF`（HTTPS） | `.env` 的 `DJANGO_CSRF_TRUSTED_ORIGINS` 加 `https://域名` |
| nginx 起不来 | 443 的证书没签（先走 4) 步签证书再 `up nginx`）；或 DOMAIN 带了前导空格 |
| 80 端口占用 | 证书 standalone 时先 `docker compose stop nginx` |
| 聊天流不动 / 一整段蹦出来 | 确认 `nginx.conf.template` 的 `location ~ stream` 的 `proxy_buffering off` 生效；重载 `nginx -s reload` |
| 聊天报上游错误 | `docker compose exec web env \| grep LLM_*` 检查 key / baseURL；看 `docker compose logs -f web` |
| MySQL OOM | 加 swap 见第四节；compose 里 `mem_limit: 480m` 兜底 |
| 上传 400 | 图片 >10MB、非图片类型或没登录；浏览器 F12 看 `/blog/api/upload/` 响应 |
