# aios

Monorepo for the services and UIs behind `fluxtopus.com`.

## 🚀 Quick Start

```bash
# 1. Configure env
cp .env.example .env

# 2. Start services
docker compose up -d --build

# 3. Seed dev users (includes admin@fluxtopus.com)
docker compose exec inkpass python scripts/seed_dev_users.py
```

**Access services (Development):**
- Tentackl API: http://localhost:8005
- Tentackl UI: http://localhost:3000
- InkPass API: http://localhost:8004
- Mimic API: http://localhost:8006
- Mimic UI: http://localhost:3001
- Marketing: http://localhost:3002

**Production URLs:**
- https://fluxtopus.com

## 📦 What's Inside

### Services

| Service | Description | Port | Tech Stack |
|---------|-------------|------|------------|
| **Tentackl** | Multi-agent workflow orchestration engine | 8005 | FastAPI, Celery, PostgreSQL, Redis |
| **InkPass** | Authentication & authorization service | 8004 | FastAPI, PostgreSQL, Redis |
| **Mimic** | Notification workflow management platform | 8006 | FastAPI, PostgreSQL |

### Structure

```text
aios/
├── apps/                      # Independent deployable services
│   ├── tentackl/              # Task orchestration
│   ├── inkpass/               # Auth service
│   └── mimic/                 # Notification service
├── frontends/                 # UI applications
│   ├── tentackl-ui/           # Workflow visualization
│   ├── mimic-ui/              # Notification UI
│   └── aios-landing/          # Marketing site
├── packages/                  # Shared SDKs and utilities
│   ├── aios-agent/
│   ├── inkpass-sdk-python/
│   ├── mimic-sdk-python/
│   └── aios-stripe/
├── skills/                    # Repository-managed Codex skills
│   └── aios-agent-package-maintainer/
├── docker-compose.yml         # Development: all services
└── docs/
    └── architecture/          # Architecture docs
```

## 🛠️ Common Commands

### Development

```bash
make dev
docker compose logs -f
make stop
```

### Testing

```bash
make test-all
```

## 📈 Optional Monitoring (Local)

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

- Grafana: `http://localhost:3003` (admin / admin)
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`

## 📚 Documentation

- Tentackl: `apps/tentackl/README.md`
- InkPass: `apps/inkpass/README.md`
- Mimic: `apps/mimic/README.md`
- Package release skill: `skills/aios-agent-package-maintainer/SKILL.md`

## 🔒 Security

**Never commit:**
- `.env` files with real secrets
- API keys
- Database passwords
- Encryption keys

**Generate secure keys:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 🤝 Contributing

1. Create a branch
2. Make changes
3. Run `make test-all`

## 📊 Service Matrix

| Feature | Tentackl | InkPass | Mimic |
|---------|----------|---------|-------|
| **Language** | Python | Python | Python |
| **Framework** | FastAPI | FastAPI | FastAPI |
| **Database** | PostgreSQL | PostgreSQL | PostgreSQL |
| **Cache** | Redis | Redis | - |
| **Background Jobs** | Celery | - | - |
| **Frontend** | React | - | Next.js |
| **Auth Required** | Optional | - | Yes |
| **External APIs** | OpenRouter, MCP | - | Discord, Slack |

## 🐛 Troubleshooting

**Services won't start:**
```bash
docker compose logs -f
```

**Port conflicts:**
Edit `docker-compose.yml` and change port mappings.

**Database errors:**
```bash
docker compose down -v
docker compose up -d --build
```

**More help:**
- Open an issue on GitHub

## 📝 License

MIT. See `LICENSE`.

## 🙏 Support

- **Documentation**: See `docs/` folder
- **Issues**: GitHub Issues
- **Service Docs**: Check `apps/*/README.md`

---

**Quick Commands Cheatsheet:**

```bash
make help           # Show all available commands
make dev            # Start everything
make test-all       # Test everything
make stop           # Stop everything
make logs           # View logs
```

**Remember:** Local development uses `docker-compose.yml`. For a standalone Tentackl stack, use `docker-compose.standalone.yml`.
