# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

医疗建筑设计部（中建西北院）内部 Wiki 知识库，基于 BookStack + 自研审核排名系统，Docker Compose 一键部署。

## 架构

```
BookStack (PHP Wiki) ← 知识浏览、搜索、页面管理
    ↕ REST API
Flask 排名+审核服务 ← 提交审核流程、贡献排行榜、Excel导出
    ↕
SQLite (ranking.db) ← 提交记录、排名快照
MySQL 8.0 ← BookStack 数据存储
```

三个 Docker 容器：`bookstack`(端口6875)、`bookstack_db`、`bookstack_ranking`(端口6876)

## 目录结构

```
bookstack/
├── docker-compose.yml      # 三容器编排
├── .env.example            # 环境变量模板
├── backup.sh               # 每日备份脚本
├── ranking/                # Flask 排名+审核服务
│   ├── app.py              # 路由：排名、提交、审核、导出
│   ├── models.py           # SQLite 模型：snapshots、submissions
│   ├── calculator.py       # BookStack API 采集 → 字数计算
│   ├── bookstack_client.py # BookStack REST API 封装
│   ├── Dockerfile
│   └── templates/          # Jinja2 页面模板
└── migration/
    └── migrate.py          # SQLite → BookStack 数据迁移
docs/                       # 知识库 Markdown 源文件（88篇）
```

## 常用命令

```bash
# 部署
cd bookstack && cp .env.example .env && docker compose up -d

# 重建排名服务（修改代码后）
docker compose build ranking && docker compose up -d ranking

# 手动触发排名采集
curl -X POST http://localhost:6876/api/collect

# 导入 docs/ 到 BookStack
cd migration && python3 migrate.py --db /path/to/knowledge.db \
  --url http://localhost:6875 --token-id TOKEN_ID --token-secret TOKEN_SECRET
```

## 关键页面路由（排名服务 app.py）

| 路由 | 用途 |
|------|------|
| `/` | 排名首页（周/月/年/总） |
| `/submit` | 普通用户提交修改 |
| `/my-submissions?email=` | 查询个人提交记录 |
| `/admin/review?pwd=` | 管理员审核面板 |
| `/admin/approve/<id>` | 批准并发布到 BookStack |
| `/admin/reject/<id>` | 驳回 |
| `/leaderboard` | 贡献排行榜（基于审核通过的字数） |
| `/export?period=` | 导出 Excel |
| `/api/collect` | 手动触发数据采集 |

## 业务流程

1. 普通用户在 BookStack 中为 **Viewer（只读）**，不能直接编辑
2. 修改内容通过 `/submit` 提交，存入 `submissions` 表（status=pending）
3. 管理员在 `/admin/review` 审核，批准后通过 BookStack API 自动发布
4. 审核通过的字数计入贡献排行榜

## BookStack API 认证

```
Authorization: Token {token_id}:{token_secret}
```

`bookstack_client.py` 封装了分页查询、CRUD 操作。

## 部署注意事项

- BookStack 内部 `.env` 在容器 `/config/www/.env`，docker-compose 环境变量**不会**自动覆盖它，首次部署需手动修改
- `SESSION_SECURE_COOKIE=false` 必须设置（HTTP 环境），否则登出后 419
- `APP_KEY` 必须正确设置，否则 CSRF 验证失败
- 首页设置：数据库 `settings` 表 `app-homepage-type=shelves`, `app-homepage=491`
- NAS Docker 需配置代理才能拉取镜像

## 当前部署状态

- **运行位置：** NAS (192.168.1.69) Docker
- **知识库内容：** 1个书架、11本书（第一章~第十章+附录）、88篇文章
- **计划：** 后续迁移到云服务器
