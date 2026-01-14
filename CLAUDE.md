# Google Calendar MCP

MCP сервер для интеграции с Google Calendar. Поддерживает управление событиями, проектами (time tracking), контактами.

## Production Server

- **Host:** `157.173.109.132`
- **User:** `root`
- **Container:** `google-calendar-mcp`
- **Port:** `8005` (external) -> `8000` (internal)
- **App path:** `/root/apps/google-calendar-mcp/`
- **Public URL:** `https://viredge.com/calendar/mcp`

## Database

- **Container:** `shared-postgres`
- **Host (docker):** `shared-postgres` или `travel-postgres`
- **Port:** `5432`
- **Database:** `google_calendar_mcp`
- **User:** `travel`

## Key URLs

| Endpoint | URL |
|----------|-----|
| Health | `https://viredge.com/calendar/mcp/health` |
| OAuth callback | `https://viredge.com/calendar/mcp/oauth/callback` |
| Export files | `https://viredge.com/calendar/mcp/export/{uuid}` |
| MCP endpoint | `https://viredge.com/calendar/mcp/mcp` |

## Environment Variables

На сервере: `/root/apps/google-calendar-mcp/.env`

Ключевые переменные:
- `GCAL_MCP_API_KEY` — API ключ для аутентификации
- `GCAL_MCP_SERVER_BASE_URL` — базовый URL сервера (`https://viredge.com/calendar/mcp`)
- `EXPORT_BASE_URL` — базовый URL для ссылок на экспорт (`https://viredge.com/calendar/mcp`)
- `GCAL_MCP_OAUTH_*` — OAuth credentials

## Deploy

Автоматический деплой через GitHub Actions при push в `main`.

Ручной перезапуск на сервере:
```bash
ssh root@157.173.109.132
cd /root/apps/google-calendar-mcp
docker compose -f docker-compose.prod.yml up -d
docker logs google-calendar-mcp --tail 50
```

## Project Structure

```
src/google_calendar/
├── server.py              # FastAPI + MCP сервер
├── settings.py            # Настройки из env
├── export_router.py       # Endpoint /export/{uuid} для скачивания файлов
├── oauth_server.py        # OAuth endpoints
├── api/
│   └── client.py          # Google Calendar API client
├── db/
│   ├── connection.py      # PostgreSQL connection pool
│   └── schema.sql         # Database schema
└── tools/
    ├── calendars.py       # Calendar management
    ├── events.py          # Event CRUD
    ├── availability.py    # Freebusy, find slots
    ├── attendees.py       # Attendee management
    ├── intelligence.py    # Weekly brief
    ├── projects/          # Time tracking (reports, norms)
    │   ├── manage.py      # Main tool entry point
    │   └── report.py      # Report generation, Excel export
    └── contacts/          # Contact management
        ├── manage.py      # Main tool entry point
        └── report.py      # Contact reports, Excel export
```

## Reports & Export

Отчёты генерируются в `/data/reports/{uuid}.xlsx` с TTL 1 час.

Ссылка формируется как: `{EXPORT_BASE_URL}/export/{uuid}`

Endpoint `/export/{uuid}`:
- Не требует аутентификации (UUID = токен доступа)
- Возвращает 404 если файл не найден
- Возвращает 410 если файл истёк

### Cleanup expired files

Background task в `export_router.py`:
- Запускается каждые 15 минут
- Удаляет файлы из `/data/reports/` у которых `expires_at < NOW()`
- Помечает записи в БД как `is_deleted = TRUE`
- Логирует количество удалённых файлов

Проверить работу:
```bash
ssh root@157.173.109.132 "docker logs google-calendar-mcp 2>&1 | grep -i cleanup"
```

## Testing Locally

```bash
# Запуск локально
python -m google_calendar.server

# Проверка синтаксиса
python -m py_compile src/google_calendar/server.py
```

## Common Issues

### Ссылки на экспорт не работают
1. Проверь `EXPORT_BASE_URL` в `.env` на сервере
2. URL должен включать `/calendar/mcp` prefix
3. После изменения — перезапусти контейнер

### OAuth не работает
1. Проверь `GCAL_MCP_OAUTH_REDIRECT_URI` совпадает с Google Cloud Console
2. Redirect URI: `https://viredge.com/calendar/mcp/oauth/callback`
