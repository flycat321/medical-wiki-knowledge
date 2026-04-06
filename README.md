# 医疗建筑EPC设计管理知识库

中建西北院医疗设计部内部知识库系统，基于 BookStack + 自研审核排名系统。

## 架构

- **BookStack** — 开源 Wiki 平台，提供知识浏览、搜索
- **审核排名服务** — Flask 应用，提供提交审核流程 + 贡献排行榜
- **MySQL** — BookStack 数据存储
- 三者通过 Docker Compose 一键部署

## 快速部署

```bash
cd bookstack
cp .env.example .env
# 编辑 .env 填入实际密码和 API Token
docker compose up -d
```

## 目录结构

```
├── CLAUDE.md              # 项目记忆文件（Claude Code 跨会话上下文）
├── bookstack/             # 部署配置和排名系统代码
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── backup.sh          # 每日自动备份脚本
│   ├── ranking/           # Flask 排名+审核服务
│   │   ├── app.py
│   │   ├── models.py
│   │   ├── calculator.py
│   │   ├── bookstack_client.py
│   │   ├── Dockerfile
│   │   └── templates/     # 页面模板
│   └── migration/         # 数据迁移脚本
│       └── migrate.py
└── docs/                  # 知识库源文件（Markdown）
    ├── 第一章_总则/
    ├── 第二章_前期策划与资料对接/
    ├── ...
    └── 附录/
```

## 使用流程

### 普通用户
1. 登录 BookStack 浏览知识（只读）
2. 通过排名服务提交修改（`/submit`）
3. 等待管理员审核

### 管理员
1. 审核面板查看待审核提交（`/admin/review`）
2. 批准 → 自动发布到 BookStack
3. 驳回 → 填写意见反馈给用户
