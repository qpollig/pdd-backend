# PDD Test Platform API — Фаза 1 (MVP)

Асинхронный бэкенд на FastAPI для B2C-платформы ПДД-тестов. Реализован **строго** скоуп Фазы 1
из ТЗ: Auth (OAuth), Контент (темы/билеты/вопросы), Плеер тестов, Жизни (freemium), Подписки и биллинг.

Промокоды, рефералки, реклама, стрики, "Марафон 800 вопросов" и "Экзамен Автошколы" **не реализованы** —
они вне скоупа Фазы 1 согласно ТЗ и вынесены во 2-ю фазу.

## Стек

Python 3.12, FastAPI (async/await), SQLAlchemy 2.0 AsyncIO + asyncpg, Alembic, Pydantic v2,
APScheduler (фоновые джобы), Docker / docker-compose.

## Быстрый старт (Docker)

```bash
cp .env.example .env
docker compose up --build
```

API поднимется на `http://localhost:8000`, миграции Alembic применяются автоматически при старте
контейнера `api`. Документация Swagger — `http://localhost:8000/docs`.

## Локальный запуск без Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # укажите DATABASE_URL на локальный Postgres
alembic upgrade head
uvicorn app.main:app --reload
```

## Структура проекта

```
app/
  core/        # конфиг, БД (async engine/session), JWT-безопасность
  models/      # SQLAlchemy 2.0 модели (Mapped/mapped_column)
  schemas/     # Pydantic v2 схемы запросов/ответов
  api/v1/      # роутеры эндпоинтов
  services/    # бизнес-логика (репозитории, плеер, жизни, биллинг, OAuth, эквайринг)
  workers/     # фоновые джобы + APScheduler wiring
alembic/       # миграции (0001_initial — полная схема Фазы 1)
```

## Реализованная логика (соответствие ТЗ)

### 1. Auth
`POST /api/v1/auth/oauth/{provider}` (`yandex` | `vk`) — обмен `code` на токен провайдера,
запрос профиля, create-or-update `users`, выдача JWT.

### 2. Контент
`GET /api/v1/topics` — список тем + 40 билетов. Поле `is_correct` в ответах на вопросы отдаётся
только в режимах `theory` и `errors`; в `gibdd_exam` скрывается до `/finish`
(см. `app/services/serializers.py::build_question_out`).

### 3. Плеер / Test Sessions
- `POST /api/v1/tickets/session/start` — старт сессии (`theory` / `gibdd_exam` / `errors`).
- `POST /api/v1/tickets/session/answer`:
  - неверный ответ → списание 1 жизни для Free (Premium не трогаем);
  - режим `errors`: верный ответ → запись удаляется из `user_errors`;
  - режим `gibdd_exam`: при ошибке подмешиваются +5 доп. вопросов из того же `topic_id`,
    что и вопрос с ошибкой (лимит: 2 ошибки / 10 доп. вопросов суммарно — настраивается в `Settings`).
- `POST /api/v1/tickets/session/finish` — завершение сессии, фиксация `correct_count` / `errors_count`,
  для `gibdd_exam` — расчёт `passed`.

### 4. Жизни (Freemium)
Free: `lives_current = lives_max = 5` по умолчанию. Списание — только при неверном ответе.
Ежесуточный сброс до 5 в 00:00 UTC — cron-джоба `app/workers/lives_reset.py` через APScheduler.
При `lives_current == 0` и `is_premium == False` — `403 OUT_OF_LIVES` на старте новой сессии.
Premium — не ограничены.

### 5. Подписки и биллинг
- `POST /api/v1/billing/checkout/init` — инициализация оплаты 1 ₽ / 3 дня триала
  (заготовка под ЮKassa API, `save_payment_method=true` для получения rebill-токена).
- `POST /api/v1/billing/webhook` — обработка вебхука эквайринга: сохраняет `rebill_id`,
  ставит `is_premium = True`, создаёт/обновляет `subscriptions` (триал 3 дня).
  **Важно:** перед продакшеном нужно добавить проверку подписи/источника вебхука
  (см. TODO-комментарий в `app/api/v1/endpoints/billing.py`).
- Фоновая джоба `app/workers/billing_recurring.py` (по умолчанию — раз в час, настраивается
  `BILLING_WORKER_INTERVAL_MINUTES`): ищет подписки с `paid_until <= now()` и `auto_renew == True`,
  списывает 299 ₽ по `rebill_id`. Успех → `paid_until += 30 дней`. Ошибка →
  `is_premium = False`, `status = cancelled`.
- `POST /api/v1/subscriptions/cancel` — отключение `auto_renew`, Premium сохраняется до конца
  оплаченного периода.

## Наполнение контентом (темы/билеты/вопросы)

Таблицы `topics`, `tickets`, `questions`, `answers` создаются миграцией, но **не заполняются** —
контент (40 официальных билетов ПДД, вопросы, изображения знаков) не был частью присланного ТЗ
и должен быть загружен отдельным сид-скриптом/импортом из имеющегося у вас источника данных.

## Что осознанно не реализовано (вне скоупа Фазы 1)

Промокоды, реферальная программа, просмотр рекламы за жизни, стрики/огонёчки,
"Марафон 800 вопросов", "Экзамен Автошколы" — таблицы и поля под эти фичи не создавались.

## Известные точки для доработки перед продакшеном

1. Проверка подписи вебхука эквайринга (сейчас — TODO, любой POST на `/billing/webhook`
   с валидным `metadata.user_id` считается доверенным).
2. Реальные ключи `ACQUIRER_SHOP_ID` / `ACQUIRER_SECRET_KEY` — без них `checkout/init` возвращает
   мок-ссылку для локальной разработки.
3. Rate limiting на `auth`/`billing` эндпоинты.
4. Идемпотентность вебхука по `external_payment_id` (сейчас уникальный индекс защищает от дублей
   на уровне БД, но повторная доставка вебхука не возвращает отдельный флаг "already processed").
