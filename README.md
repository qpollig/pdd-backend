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
`GET /api/v1/topics` — список тем + билеты. Поле `is_correct` в ответах на вопросы отдаётся
только в режимах `theory` и `errors`; в `gibdd_exam` скрывается до `/finish`
(см. `app/services/serializers.py::build_question_out`).

- **Только категория «A, B».** Каталог, счётчики вопросов в темах и случайный билет «Экзамена
  ГИБДД» ограничены категорией `A_B` — список `content_repo.ACTIVE_TICKET_CATEGORIES` (добавить
  `C_D` туда → вернётся в выдачу, менять запросы не нужно). Сейчас `/topics` отдаёт 40 билетов A_B.
- Каждый элемент `topics[]` содержит `questions_count` — число вопросов темы в разрезе активных
  категорий (сумма по 26 темам ≈ 794 — «банк 800 вопросов»).
- `GET /api/v1/questions/{id}/image` — **без Bearer-авторизации** (обычный `<img src>` не может
  передать заголовок `Authorization`; доступ к вопросу уже проверен на уровне сессии, а картинка
  не эксклюзивна). Ответ помечен `Cache-Control: immutable`. Переезд на CDN — только правка
  формирования `image_url` в `serializers.py`, фронтенд не трогается.

### 3. Плеер / Test Sessions
- `POST /api/v1/tickets/session/start` — старт сессии (`theory` / `gibdd_exam` / `errors` /
  `favorites`). Для `gibdd_exam` `ticket_id` **не обязателен**: если фронт его не передал,
  backend сам берёт случайный билет активной категории (реальный экзамен — случайный билет
  из 20 вопросов). `theory` по-прежнему требует `ticket_id` или `topic_id`.
- `POST /api/v1/tickets/session/answer`:
  - неверный ответ → списание 1 жизни для Free (Premium не трогаем);
  - режим `errors`: верный ответ → запись удаляется из `user_errors`;
  - режим `gibdd_exam`: при ошибке подмешиваются +5 доп. вопросов из того же `topic_id`,
    что и вопрос с ошибкой (лимит: 2 ошибки / 10 доп. вопросов суммарно — настраивается в `Settings`).
- `POST /api/v1/tickets/session/finish` — завершение сессии, фиксация `correct_count` / `errors_count`,
  для `gibdd_exam` — расчёт `passed`.

### 4. Жизни (Freemium)
Free: `lives_current = lives_max = 10` по умолчанию (ТЗ v1.5, раздел 4.7). Списание — только
при неверном ответе. Лимит хранится в колонке `users.lives_max` (не в константе кода), чтобы
менять его под акции без релиза; `DEFAULT_LIVES_MAX` — лишь дефолт для новых пользователей.
Ежесуточный сброс до `lives_max` в 00:00 UTC — cron-джоба `app/workers/lives_reset.py` через
APScheduler.
При `lives_current == 0` и `is_premium == False` — `403 OUT_OF_LIVES` на старте новой сессии.
Premium — не ограничены.

`GET /api/v1/users/me` отдаёт `lives_reset_at` (когда жизни сбрасывались в последний раз) и
`lives_regen_at` (ближайшие 00:00 UTC — когда сбросятся снова; `null` для Premium) — чтобы
фронт мог показать таймер восстановления в ЛК и на дашборде.

> ТЗ v1.5 в разделе 4.7 описывает более точную модель восстановления («+1 жизнь через 24 ч
> с момента, когда жизни опустились ниже максимума», поле `users.lives_regen_at`) и списание
> жизней во всех режимах. В Фазе 1 реализован упрощённый вариант из плана MVP — ежесуточный
> сброс и списание в режимах с жизнями. Уточнённая модель — доработка следующей итерации.

### 5. Подписки и биллинг
- `POST /api/v1/billing/checkout/init` — инициализация оплаты 1 ₽ / 3 дня триала
  (заготовка под ЮKassa API, `save_payment_method=true` для получения rebill-токена).
- **Заглушка ЮKassa (пока нет `ACQUIRER_SHOP_ID`/`ACQUIRER_SECRET_KEY`).** `checkout/init`
  возвращает `confirmation_url` на встроенную страницу
  `GET /api/v1/billing/mock-pay/{payment_id}` (HTML, без авторизации, `include_in_schema=false`).
  Кнопка «Оплатить» → `POST /api/v1/billing/mock-pay/{payment_id}/complete`: активирует триал
  (как это сделал бы вебхук) и делает `303` redirect на `BILLING_RETURN_URL?checkout=success`.
  Идемпотентно (повторный `complete` не плодит подписки). Абсолютный адрес страницы собирается
  из `PUBLIC_API_BASE_URL`. Как только заданы реальные ключи эквайринга — заглушка отдаёт `404`,
  `checkout/init` уходит на настоящий `api.yookassa.ru`.
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

## Развёртывание на dev-сервере (чек-лист)

1. **`.env` на сервере** (chmod 600, не в git):
   - `ENVIRONMENT=dev` — при этом backend не стартует с дефолтным `JWT_SECRET_KEY`.
   - `JWT_SECRET_KEY=` — реальный секрет: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
   - `CORS_ALLOW_ORIGINS=` — домен(ы) фронтенда dev-сервера (или `*` на время интеграции).
   - `OAUTH_REDIRECT_URI=` — реальный `redirect_uri` dev-домена.
   - OAuth: либо задать `YANDEX_CLIENT_ID/SECRET` и `VK_CLIENT_ID/SECRET` из кабинетов
     Yandex OAuth / VK ID (с тем же `redirect_uri`), либо на время выставить
     `OAUTH_ALLOW_MOCK=true` — тогда вход работает без регистрации приложений
     (детерминированный фейковый профиль по `code`). **`OAUTH_ALLOW_MOCK` не включать в prod.**
2. `docker compose up -d --build` — миграции Alembic (включая `0005_lives_default_10`)
   применяются автоматически командой контейнера `api`.
3. **Наполнить БД контентом** (иначе `/api/v1/topics` пустой):
   ```bash
   docker compose exec api python -m scripts.seed_pdd_content
   ```
   Скрипт тянет билеты/вопросы/картинки из открытого репозитория по сети — серверу нужен
   исходящий доступ в интернет (GitHub / raw.githubusercontent.com).

Не блокирует dev, но обязательно до prod: проверка подписи вебхука эквайринга
(`app/api/v1/endpoints/billing.py`, сейчас TODO) — без неё любой POST на `/billing/webhook`
с валидным `metadata.user_id` выдаёт Premium.

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
