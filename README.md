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

#### 实测：Ubuntu 20.04 (focal) 上脚本失败与修复

**失败现象与因果链**（RackNerd 这台机是 focal，2025-05 起 EOL）：

```
DEPRECATION WARNING: This Linux distribution (ubuntu focal) reached end-of-life ...
E: Unable to locate package docker-model-plugin
Failed to enable unit: Unit file docker.service does not exist.
```

脚本虽警示 focal 已停维护，但仍继续执行且默认安装列表里带了新组件
`docker-model-plugin`（2025 年新增的 AI Model Runner）——这个包在 **focal 对应的 Docker
官方 apt 源里根本不存在**，apt 整单拒绝 → 一个包都没装上 → 后续 enable 报无此 unit。
是"系统太老 + 新组件缺收录"，不是网络或命令问题。

**修复**：跑过脚本后官方源其实已经配好
（`/etc/apt/sources.list.d/docker.list` 指向 focal stable），
跳过缺的组件手动装其余全套即可：

```bash
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

docker --version            # Docker 28.1.1
docker compose version      # v2.35.1 —— compose 流程必需的最关键一项
docker run --rm hello-world # 拉镜像验一把（说明 Docker Hub 网络也通）
```

> focal EOL 只是没有宿主机的 apt 安全更新了；对我们影响极小——博客跑在自含镜像里，
> 宿主机只承担转发与存储。要根除可以以后空闲时 `do-release-upgrade` 升 22.04/24.04，
> 不要和部署挤在一起做。

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
>
> **前端修复记录（2026-11-11）**：修两个前台 bug——
> ① 列表重复：`loadPosts` 没有时序保护，搜索防抖/切换分类的并发请求里"慢的旧结果晚回"
>    会把旧查询结果也 append 进列表（表现为标题重复出现多次）。修复：请求加
>    时序令牌 `listReqSeq/detailReqSeq`，过期响应直接丢弃（详情同样保护）。
> ② 点赞"变红色矩形"：点赞成功后按钮被切成 `btn-danger` 全红底块，观感差。修复：
>    改为 `setLikeState()`——按钮保持 `btn-outline-danger` 描边，只把心形图标
>    `bi-heart → bi-heart-fill + text-danger`（实心红心）并禁用按钮。
> ③ 由于 CF/浏览器会缓存 `/static/js/blog.js`，模板引用改为
>    `blog.js?v=20261111`——**以后每次改 JS/CSS，记得同步升版本号**（或改文件名），
>    否则线上会一直给旧缓存。

### 7) 实录：tiandachui.xyz 一次配置全记录（2026-11-10 实测）

以上 0)~6) 是通用教程；下面是本次在 RackNerd（Ubuntu 20.04）真实执行的完整顺序，
每步附说明与踩坑注，照抄即可复现。

#### 7.1 仓库归位到 /opt/personal-site

README 后续所有命令（备份 cron / 证书续期 / 更新上线）都以 `/opt/personal-site` 为基准目录。
如果 clone 到了家目录（尤其 clone 出来还套了一层子目录 `~/blog/personal-site`，
git clone 默认用仓库名建目录），先归位：

```bash
# 确认位置后整体移动（.git 目录随目录走，历史/远端配置不丢）
mv ~/blog/personal-site /opt/personal-site
rmdir ~/blog                     # 清掉空壳
cd /opt/personal-site

git pull --ff-only               # 顺手把 clone 之后又合入的文档提交拉到最新
git log --oneline -3             # 核对 HEAD 是否为 origin/main 同版
```

#### 7.2 DNS 预检（签证书前必做）

Let's Encrypt 要从公网回连你域名，先确认解析已生效再动手：

```bash
getent hosts tiandachui.xyz      # 输出 107.173.149.10 即已生效；NO-OUTPUT 就是 DNS 还没生效
ss -tlnp | grep ":80 "           # 无输出 = 80 空闲（standalone 签证书的硬要求）
```

#### 7.3 写 .env（随机密钥 + 本站域名）

`nano .env` 逐项手改也行；下面的 sed 一步到位。
⚠️ 大坑：`cp .env.example .env` 里 `DB_HOST / DB_NAME / DB_USER / DB_PASSWORD /
DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS` 都是 **`#` 注释状态**——
只替换"未注释行"会替换不到它们（sed 按 `^KEY=` 匹配，`#` 开头匹配不上，
DB 配置就悄悄没生效）。要把注释行**改写为启用状态**，不是只追加：

```bash
cp .env.example .env
chmod 600 .env                                          # .env 含密码，只 root 可读

# 随机三件套：SECRET_KEY / DB 密码 / 管理员密码
SK=$(python3 -c 'import secrets;print(secrets.token_urlsafe(38))')
DBPW=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
SUPPW=$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')

sed -i -e "s/^DJANGO_SECRET_KEY=.*/DJANGO_SECRET_KEY=$SK/" \
       -e "s/^DJANGO_DEBUG=.*/DJANGO_DEBUG=false/" \
       -e "s/^DOMAIN=.*/DOMAIN=tiandachui.xyz/" \
       -e "s/^DB_ENGINE=.*/DB_ENGINE=mysql/" \
       -e "s/^#DB_PORT=.*/DB_PORT=3306/" \
       -e "s/^#DB_HOST=.*/DB_HOST=db/" \
       -e "s/^#DB_NAME=.*/DB_NAME=personal_site/" \
       -e "s/^#DB_USER=.*/DB_USER=site/" \
       -e "s/^#DB_PASSWORD=.*/DB_PASSWORD=$DBPW/" \
       .env

# ALLOWED_HOSTS / CSRF 在模板里多半整行都被注释——确认存在则改写，不存在则插入
grep -q "^DJANGO_ALLOWED_HOSTS=" .env || \
  sed -i "/^DJANGO_DEBUG=false/a DJANGO_ALLOWED_HOSTS=tiandachui.xyz,web,localhost" .env
grep -q "^DJANGO_CSRF_TRUSTED_ORIGINS=" .env || \
  sed -i "/^DJANGO_ALLOWED_HOSTS=/a DJANGO_CSRF_TRUSTED_ORIGINS=https://tiandachui.xyz" .env

# 附：管理员三件套（createsuperuser --noinput 自动读取，见 7.6）
cat >> .env <<EOF
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=18041033@qq.com
DJANGO_SUPERUSER_PASSWORD=$SUPPW
EOF
```

生效检查（密码行打码后应看到下面的 16 行）：

```bash
grep -vE "^\s*#" .env | grep -vE "^\s*$" | \
  sed -E "s/^(DJANGO_SECRET_KEY|DB_PASSWORD|DJANGO_SUPERUSER_PASSWORD)=.*/\1=<hidden>/"
# 期望：DJANGO_SECRET_KEY / DOMAIN / DJANGO_DEBUG=false / DJANGO_ALLOWED_HOSTS /
#       DJANGO_CSRF_TRUSTED_ORIGINS / DB_ENGINE=mysql / DB_HOST=db / DB_NAME /
#       DB_USER / DB_PASSWORD / LLM_BASE_URL / LLM_MODEL / LLM_API_KEY(空,后填) /
#       UVICORN_WORKERS / DJANGO_SUPERUSER_*
```

`LLM_API_KEY=` 暂留空：博客、记账、HTTPS 全部正常可用；AI 问答 `/chat/` 待填 key 后生效。

#### 7.4 首次构建并启动 db + web

```bash
docker compose up -d --build db web    # 首次会拉 python:3.12-slim + mysql:8.0 镜像并 pip 安装，等几分钟
docker compose ps                      # db 应显示 (healthy)；web 起来即 OK
docker compose logs --no-color web | tail -20
```

关键判据（logs 里看）：

- `Apply all migrations ... OK`（migrate 完成）
- `138 static files copied to '/app/staticfiles'`（collectstatic 完成）
- `Uvicorn running on http://0.0.0.0:8000`（应用已起）
  > compose 的 db 服务带 healthcheck，`db` 的 STATUS 变 `(healthy)` 后 web 才被正式拉起。

#### 7.5 首次签发证书（standalone，趁 80 空闲）

```bash
docker compose --profile tls run --rm -p 80:80 certbot certonly --standalone \
  --agree-tos --email 18041033@qq.com -d tiandachui.xyz
# 成功标志：
#   Certificate successfully received.
#   Certificate is saved at: /etc/letsencrypt/live/tiandachui.xyz/fullchain.pem
#   Key is saved at:         /etc/letsencrypt/live/tiandachui.xyz/privkey.pem
#   Expires on 2027-02-08（90 天，之后 cron 周一自动续期，见第五节）
```

#### 7.6 启动 nginx + 端到端验证 + 建管理员

```bash
docker compose up -d nginx

curl -sI https://tiandachui.xyz        # HTTP/2 302 → 根路径跳 /blog/，即整条 TLS→nginx→web 已通
curl -s https://tiandachui.xyz/blog/ | head -c 300   # 输出博客 HTML 说明页面真实渲染

# 管理员：.env 已预置 DJANGO_SUPERUSER_*，--noinput 全自动（账号 admin/邮箱/强随机密码在 .env 里）
chmod 600 .env   # 确认过
docker compose exec -T web python manage.py createsuperuser --noinput
docker compose exec -T web python manage.py shell -c \
  "from django.contrib.auth.models import User; print([(u.username,u.is_superuser) for u in User.objects.all()])"
# [会看到 [('admin', True)]]
```

#### 7.7 本次完成时的系统状态（对照检查）

| 组件 | 状态 |
| --- | --- |
| `docker compose ps` | site-db Up (healthy) / site-web Up / site-nginx Up |
| Docker | 28.1.1 + Compose v2.35.1 + buildx v0.23.0（focal 手动安装，见三-1） |
| 证书 | `live/tiandachui.xyz/`，有效期至 2027-02-08，周一 03:30 cron webroot 续期 |
| 管理员 | `admin`（`DJANGO_SUPERUSER_PASSWORD` 在 `.env`，登录后建议 admin 后台改一次密码） |
| HTTPS | `HTTP/2`，nginx 1.27 反代 web:8000 |
| CDN/访问 | **Cloudflare 橙云已开（Proxied）**：堵住"本地→美国 IP 直连丢包"的问题；DNS 解析出 `104.21.x/172.67.x`，`Server: cloudflare`，`/` 302、`/blog/`、`/admin/login/`、`/static/*` 全 200（2026-11-10 17:03 实测） |
| 待办 | `.env` 填 `LLM_API_KEY` 后重启 web（`docker compose up -d web`）激活 `/chat/`；装第五节 crontab；swap（第四节） |

#### 7.8 橙云开完后的端到端验证（2026-11-10 17:03 实测全绿）

DNS 应解析出 Cloudflare 边缘地址（**不再是源站 IP** `107.173.149.10`）：

```powershell
# 本机（Windows）
ipconfig /flushdns                 # 先清缓存：橙云前很可能缓存过直连死 IP
(Resolve-DnsName tiandachui.xyz).IPAddress   # 期望：104.21.x / 172.67.x / 2606:4700:…（CF 边缘）
```

HTTPS 响应头应出现 `Server: cloudflare`：

```powershell
curl.exe -sI --connect-timeout 15 --max-time 30 https://tiandachui.xyz/blog/
# 期望：HTTP/1.1 200 OK  +  Server: cloudflare
```

全域抽查（本次实测全部通过）：

```powershell
curl -sI https://tiandachui.xyz/                    # 302 Found（根路径跳 /blog/；明文 http:// 先被 CF 301 到 https）
curl -sI https://tiandachui.xyz/blog/               # 200
curl -sI https://tiandachui.xyz/admin/login/        # 200（登录墙）
curl -sI https://tiandachui.xyz/static/css/site.css # 200
```

#### 7.9 "开了橙云还是打不开"——本地侧排查三板斧（实测踩全）

服务器端确认正常（VPS 内自测 + Let's Encrypt 能签）后，本机按序排查以下三点：

1. **本机 DNS 缓存残留旧直连 IP**：橙云前浏览器/系统缓存过 `107.173.149.10`（那条直连线路是黑洞）。
   ```powershell
   ipconfig /flushdns        # 每次改动 Cloudflare DNS 记录后都该跑一次
   ```
2. **hosts 文件钉过旧 IP**（flush 清不掉 hosts）：检查一遍有没有把网站域钉死。
   ```powershell
   Select-String "$env:SystemRoot\System32\drivers\etc\hosts" -Pattern "tiandachui|107.173|104.21"
   # 本次实测存在：104.21.40.187 ssh.tiandachui.xyz
   # —— 这是早年给 SSH 隧道钉的缓存，只影响 ssh 主机名，与网站主域无关，不影响访问；可留。
   # 若钉的是 "tiandachui.xyz 本身"，必须删掉那一行再 ipconfig /flushdns。
   ```
3. **IPv6 优先卡住**：实测本机 IPv6 到 CF 边缘不通
   （`Test-NetConnection 2606:4700:... -Port 443` → `False`），而解析里 AAAA 在前。
  先前试 IPv6 失败再回退 IPv4，期间表现为"转圈"，重试/刷新后走 IPv4 即通。
   顽固时可临时禁用网卡的 IPv6 协议栈。
4. **慢 ≠ 坏**：免费版 CF 对国内单次 6~7 秒常见（跨境 + 边缘调度），同线路时快时慢属常态，
   不是站点故障。
5. **浏览器自己的缓存**：无痕窗口 / Ctrl+F5；早期"无法访问"页面可能被记住，刷新即愈。

排查后结论：`ipconfig /flushdns` + 等边缘记录刷新即可正常访问（/ 302、/blog/ 200、
/admin/ 200、静态 200）。

#### 7.10 新域名共存实录：tiandachuis.top + tiandachui.xyz（2026-11-11）

需求：新买 `tiandachuis.top`，与 `tiandachui.xyz` **共存**（两个都能访问，以后想主推哪个再切）。
新域名已自行接入 Cloudflare 并开橙云（DNS 解析出 CF 边缘 IP）。

**改动清单（本地代码，已提交 bfee051）：**

1. `nginx/nginx.conf.template`：80 与 443 两个 `server_name` 都改为
   `` `server_name ${DOMAIN} ${DOMAIN_OLD};` ``（DOMAIN_OLD 可选，留空时退化为单域名）。
2. `docker-compose.yml`：nginx 服务 `environment` 增加
   `DOMAIN_OLD: ${DOMAIN_OLD:-}`（模板渲染需要）。
3. `.env`（VPS 上直接 sed）：
   ```
   DOMAIN=tiandachuis.top            # 主域名（决定证书 live 目录名）
   DOMAIN_OLD=tiandachui.xyz         # 旧域名共存
   DJANGO_ALLOWED_HOSTS=tiandachuis.top,tiandachui.xyz,web,localhost
   DJANGO_CSRF_TRUSTED_ORIGINS=https://tiandachuis.top,https://tiandachui.xyz
   ```

**证书：一张含两个域的 SAN 证书**

```
docker compose --profile tls run --rm certbot certonly --webroot -w /var/www/certbot \
  -d tiandachuis.top -d tiandachui.xyz --cert-name tiandachuis.top \
  --email 18041033@qq.com --agree-tos --no-eff-email --non-interactive
# nginx 在跑 → webroot 模式（80 端口的 /.well-known/acme-challenge/ 由 nginx 直出）
# CF 橙云下照常工作：LE → CF 边缘 → 回源 80 → webroot 文件
# 产物：/etc/letsencrypt/live/tiandachuis.top/（cert-name 即 live 目录名，须与 DOMAIN 一致）
```

> **踩坑**：第一次签发 certbot 把两个域 **expand 进了已有 `tiandachui.xyz` 证书**
> （renewal conf 复用，live 目录名仍是 `tiandachui.xyz`）——而 nginx 模板写死
> `live/${DOMAIN}/`，新 DOMAIN=`tiandachuis.top` 对不上，nginx 起不来。
> 解决：`certbot delete --cert-name tiandachui.xyz --non-interactive` 删掉旧证书
> （nginx 内存里已加载的不受影响），再按上面命令用 `--cert-name tiandachuis.top`
> 重签 → live 目录与 ${DOMAIN} 一致。

**生效：**

```
docker compose up -d --force-recreate nginx   # 模板重渲染（server_name 两域 + 新证书路径）
docker compose up -d --force-recreate web     # 读新 .env（ALLOWED_HOSTS/CSRF）
```

**验证（全通过）：**

```
curl -sI https://tiandachuis.top/blog/     # HTTP/1.1 200 OK
curl -sI https://tiandachui.xyz/blog/      # HTTP/1.1 200 OK（同一张 SAN 证书）
# 证书实测：Subject CN=tiandachuis.top，SAN 含两域
```

**注意：**

- 续期 cron（`certbot renew --webroot`）自动覆盖这张双域证书，无需改。
- 新 zone 的 Cloudflare SSL/TLS 模式建议也设为 **Full (strict)**。
- 以后再加第三个域：模板不用动，`.env` 的 `server_name` 改用列表思路即可
  （或再加 `DOMAIN_OLD2`）；证书多 `-d` 一个域、`--cert-name` 保持主域。

#### 7.11 GLM 问答上线：免费模型 + 思考深度选择 + 手机端死循环修复（2026-11-11）

**① API key 配置**（VPS `.env`）：

```
LLM_API_KEY=6ad8****（用户自有 key）
LLM_MODEL=glm-5.3-flash        # 默认模型换成免费档（原默认 glm-5.3 是收费模型会报 1113）
```

**② 免费模型探针结论**（写代码前用 key 实测 `/api/paas/v4/models` + 逐个 4-token 探针）：

- `/models` 返回 12 个模型（glm-4.5 ~ glm-5.3 全系）；
- **该 key 免费可用的只有 `glm-5.3-flash` 和 `glm-5.3-flashx`**，其余全部
  `1113 余额不足或无可用资源`。
- 结论已固化：`settings.LLM_MODELS = ["glm-5.3-flash", "glm-5.3-flashx"]`
  （`.env` 里 `LLM_MODELS=` 可覆盖白名单），前端"模型"下拉只列白名单内模型。

**③ 思考深度 low/high/max 的正确参数**（探针实锤）：

- 老 API `thinking: {"type": "enabled"/"disabled"}`：`enabled` 可用，
  `disabled` 被 flash 系列拒绝（`1210 该模型始终思考，不支持关闭思考`），
  且直接传 `thinking: {"type": "low"}` 也被拒——**报错文案里提示的
  "low/high/max" 实际走的字段是 `reasoning_effort`**（OpenAI 风格参数）。
- 实测同一问题（鸡兔同笼）：`low`≈4.6s/341 tok、`high`≈7.0s/369 tok、
  `max`≈31s/1624 tok 且返回思考链 `reasoning_content` → 三档确有区分。
- 最终映射：深度下拉框 → 请求体 `{"thinking": "low|high|max"}` →
  视图校验档位 → `stream_chat(..., reasoning_effort=档位)` → 上游
  `payload["reasoning_effort"]`。

**④ 代码改动**（`de34a7a`）：

- `chat/llm_client.py`：`stream_chat(messages, model=None, reasoning_effort=None)`，
  增量从 str 改为 `(kind, text)` 元组（`kind = "content" | "reasoning"`），
  思考链不再被丢弃。
- `chat/views.py`：请求体解析 `model/thinking`；模型必须命中
  `LLM_MODELS` 白名单、thinking 必须是 low/high/max（400 拒绝）；
  SSE 新增事件 `{"thinking": "增量"}`。
- `templates/chat/index.html`：输入区上方工具条加两个下拉（模型 CPU 图标、
  思考深度灯泡图标）；`chat.js?v=20261111`。
- `static/js/chat.js`：选择经 `localStorage`（`chat.model`/`chat.thinking`）
  记忆；`data.thinking` 渲染成可折叠思考块（流式展开 → 正文开始/结束时折叠
  为"已深度思考 · 点击展开"）。
- `static/css/site.css`（`?v=20261111`）：`.chat-thinking` 样式。
- 测试 50 → 56：新增模型白名单拒绝、档位校验、model/effort 透传、
  思考链转发且不落库等 6 个用例。

**⑤ 手机端点文章"一直刷新"死循环修复**（同 commit）：

- 根因：`blog.js` 的 `openPost()` 里移动端一律 `location.href = "/blog/<id>/"`
  整页跳转，而 `init()` 恢复场景也调用 `openPost(selectedInitial, false)` ——
  用户直接打开 `/blog/3/` 时，页面加载完又把自己跳到 `/blog/3/`，无限刷新，
  文章永远渲染不出来。
- 修复：跳转分支改为 `if (mqMobile.matches && push)`——仅用户主动点击
  （`push=true`）才跳整页；恢复场景走 fetch 正常渲染（移动端右栏靠已有的
  `body.blog-detail` class 显示，机制本来就是好的）。
- 防缓存：`blog.js?v=20261111-2`。

**部署验证**（容器内直调 `stream_chat`，真实上游）：

```
MODEL: glm-5.3-flash | MODELS: ['glm-5.3-flash', 'glm-5.3-flashx']
httpx HTTP Request: POST .../chat/completions "HTTP/1.1 200 OK"
STREAM RESULT: [('content', 'ok')]
```

`/chat/` 页面渲染检查：模型/深度下拉均存在，`chat.js?v=20261111` 生效。

#### 7.12 Xray 个人代理：VLESS 双入口（CF 中转主用 + Reality 备用）（2026-11-11）

需求：在 VPS 上搭个人代理访问 Google/YouTube（自用）。实测前置条件：

- 本地直连 VPS IP（107.173.149.10）**整 IP 不可达**：443 TLS 握手三次全部
  15s 超时、22 早就是黑洞、装好 xray 后 8443 TCP 也不通 → 只有走
  Cloudflare 的链路可达（网站/SSH 均如此）。**所以主用方案必须是 CF 中转**。

**架构**（xray 以 Docker 服务加入现有 compose，`a98e4cb`/`d0fb811`）：

```
客户端 v2rayN
  ├─ 主用：VLESS+WS+TLS → tiandachuis.top:443 (CF 橙云) → nginx → xray:10086
  └─ 备用：VLESS+Reality → 107.173.149.10:8443 直连（换网络环境才可能可用）
```

**改动清单**：

1. `docker-compose.yml`：新增 `xray` 服务（镜像 `ghcr.io/xtls/xray-core`，
   发布 8443 对外；10086 仅容器内网）；nginx `environment` 增加
   `XRAY_WS_PATH`（必填，来自 .env）；nginx `depends_on` 增加 xray。
2. `nginx/nginx.conf.template`：443 server 增加
   `location ${XRAY_WS_PATH}`——非 WebSocket 升级头一律 404（防路径扫描）；
   `resolver 127.0.0.11` + 变量 `proxy_pass`（xray 重建换 IP 不用动 nginx）；
   `proxy_http_version 1.1` + Upgrade/Connection 头（WS 升级必需）。
3. `xray/config.example.json`（仓库，占位符文档）；
   真实配置 `xray/conf/config.json` 只在 VPS 生成（.gitignore 排除）。
4. `.env`（VPS）追加 `XRAY_WS_PATH=/ws-<随机hex>`。

**踩坑实录**：

- 官方镜像读 **`/usr/local/etc/xray/` 配置目录**（confdir 模式，目录下所有
  json 合并加载）且**镜像无 shell**（scratch 风格，exec sh 失败）。第一版把
  config.json 挂到 `/etc/xray/config.json` 完全没生效 → nginx 502。
  修复：`- ./xray/conf:/usr/local/etc/xray:ro` **整目录覆盖**；真实配置放
  `xray/conf/` 子目录（example 文件不在挂载路径内，避免被当配置解析）。
- 镜像启动日志警告：Reality dest 用 `www.microsoft.com` 与非 443 端口会增加
  IP 被墙概率；WS 传输层标记弃用（官方推 XHTTP）。当前保留 WS——v2rayN/
  v2rayNG/Shadowrocket 全系兼容最广，且走 CF 的 WS 是成熟组合。

**密钥生成**（VPS，真实值已写入 xray/conf/config.json）：

```
UUID=$(docker run --rm ghcr.io/xtls/xray-core uuid)
docker run --rm ghcr.io/xtls/xray-core x25519     # Private/Public
SID=$(openssl rand -hex 8)                        # Reality shortId
XRAY_WS_PATH=/ws-$(openssl rand -hex 6)           # WS 隐匿路径
```

**端到端验证（全通过）**：

```
GET  https://tiandachuis.top/ws-a27e377aaf33            → 404（普通请求被拒=隐匿）
WS   同路径 + Upgrade: websocket                        → 101 Switching Protocols
GET  https://tiandachuis.top/ws-wrongpath               → 404
回归  /blog/ 200、/admin/ 302、/static/ 200              → 网站无影响
```

**客户端导入**（Windows v2rayN / Android v2rayNG / iOS Shadowrocket 或 Streisand）：
复制 `vless://` 分享链接 → 客户端"从剪贴板导入"。链接模板见本次会话记录；
UUID/密钥泄露=完全代理权，若外泄需重新生成（uuid/x25519 + 改
xray/conf/config.json + `docker compose restart xray`）。

**补记：CF 优选 IP 对比实测（同日晚）**——手机端 652ms 延迟的定位与优化：

自建 PowerShell 优选脚本（CF 主网段随机采样 30 IP 并行 TCPing + 20s 下载窗口
`--resolve speed.cloudflare.com`）对比域名现用 IP：

| IP | ping | 下载 |
| --- | --- | --- |
| 172.67.139.143（域名） | 295ms | **478 KB/s** ✅ |
| 162.159.24.238 | 288ms | 390 KB/s |
| 198.41.214.214 | 281ms | 379 KB/s |
| 104.18.62.88 | 251ms | 157 KB/s |
| 104.21.94.191（域名） | **775ms** | **28 KB/s** ❌ |

结论：域名两个 A 记录里 **104.21.94.191 是本线路的坏边缘**（DNS 轮询命中它
就卡），172.67.139.143 反而是全场最优。方案：客户端地址从域名固定为
`172.67.139.143`（SNI/Host 仍为 tiandachuis.top，伪装不变），追加备用
`162.159.24.238`。优选结果随线路/时段漂移，明显变卡时重跑一轮即可。

**本地一键优选脚本**：`D:\cfst\cf-select.bat`（双击运行，主逻辑
`cf-select.ps1`）——自动采样测速、生成 vless 链接、最优链接自动进剪贴板、
结果存 `latest-result.txt`。复测间隔建议：卡了再跑 / 一两周一次。

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
| **服务器正常但本地网页打不开**：本机 `Test-NetConnection IP -Port 443` 成功、curl 卡在 TLS ClientHello 15 秒超时；22 端口同样不通 | 域名托管在 Cloudflare 时直接 **DNS 页开橙云（Proxied）+ SSL/TLS 模式 Full (strict)**：访问改走 Cloudflare 边缘，绕开"本地→美国 IP"被丢包的直连线路。服务器侧一切不用改；证书续期 webroot 在 CF 下照常回源 |
| 装 Docker 脚本失败：`Unable to locate package docker-model-plugin`（focal EOL 缺新组件） | 官方源已被脚本配好，跳过该包手动装其余组件：见第三节 1) 实测块 |
| `DisallowedHost` | `.env` 的 `DJANGO_ALLOWED_HOSTS` 少了你的域名或 `web` |
| 403 `CSRF`（HTTPS） | `.env` 的 `DJANGO_CSRF_TRUSTED_ORIGINS` 加 `https://域名` |
| nginx 起不来 | 443 的证书没签（先走 4) 步签证书再 `up nginx`）；或 DOMAIN 带了前导空格 |
| 80 端口占用 | 证书 standalone 时先 `docker compose stop nginx` |
| 聊天流不动 / 一整段蹦出来 | 确认 `nginx.conf.template` 的 `location ~ stream` 的 `proxy_buffering off` 生效；重载 `nginx -s reload` |
| 聊天报上游错误 | `docker compose exec web env \| grep LLM_*` 检查 key / baseURL；看 `docker compose logs -f web` |
| MySQL OOM | 加 swap 见第四节；compose 里 `mem_limit: 480m` 兜底 |
| 上传 400 | 图片 >10MB、非图片类型或没登录；浏览器 F12 看 `/blog/api/upload/` 响应 |
