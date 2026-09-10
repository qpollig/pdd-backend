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
tests/         # pytest (см. «Тесты»)
```

## Тесты

```bash
pip install -r requirements-dev.txt      # pytest, pytest-asyncio (в prod-образ НЕ идут)

# нужен запущенный Postgres (docker compose up db). Прогон:
pytest                                   # с хоста; DATABASE_URL берётся из .env
# либо внутри контейнера (надёжнее, если порт 5432 капризит на Windows):
docker compose exec api sh -c "cd /app && pip install -r requirements-dev.txt && pytest"
```

- Тесты работают в **отдельной БД** `<dbname>_test` (создаётся/удаляется автоматически на том
  же Postgres-сервере), дев-БД с реальными пользователями не трогают. Имя можно переопределить
  через `TEST_DATABASE_NAME`. Роль БД должна иметь право `CREATEDB` (у `pdd` в docker-compose есть).
- Схема поднимается один раз за сессию (`Base.metadata.create_all`), каждый тест — во вложенной
  транзакции с откатом: повторный прогон подряд без ручной очистки тоже зелёный.
- Покрыта Фаза 1 email+password (register / login / password forgot+reset) и адаптированный под
  `auth_identities` OAuth-флоу. Что осознанно не покрыто — см. `tests/` (docstrings) и сводку в PR.
- **CI (GitHub Actions) — отдельная задача на будущее**, сейчас не настроен: нужен job, который
  поднимает `postgres:15` как service-контейнер и гоняет `pytest` на каждый push/PR.

## Реализованная логика (соответствие ТЗ)

### 1. Auth

Два способа входа, оба возвращают одинаковый `TokenResponse` (`access_token` + `UserOut`) —
фронтенду не важно, каким способом вошли. Сам способ входа хранится в таблице **`auth_identities`**
(одна строка = один способ), а не в колонках `users` — это подготовка к Фазе 2, где у одного
пользователя их будет несколько (миграция `0007_email_password_auth` перенесла существующих
oauth-пользователей и убрала `users.oauth_provider/oauth_id`).

**OAuth (Yandex/VK)** — `POST /api/v1/auth/oauth/{provider}`: обмен `code` на токен провайдера,
запрос профиля, create-or-update `users` + `auth_identities(type=provider)`, выдача JWT.
Внешний контракт не менялся.

**Email + пароль:**
- `POST /api/v1/auth/register` `{email, password, name}` → создаёт `users` +
  `auth_identities(type='password')`, сразу возвращает рабочий токен.
  **Решение Фазы 1: верификация email опциональна** — `email_verified_at` остаётся `NULL`,
  auto-login не блокируется (обоснование — в комментарии `app/api/v1/endpoints/auth.py`;
  на dev-сервере SMTP заглушечный, обязательный gate сделал бы register→login нерабочим).
  Полноценный verify-флоу — Фаза 2.
- `POST /api/v1/auth/login` `{email, password}` → таймсейф-проверка bcrypt-хеша; единый
  `401 INVALID_CREDENTIALS` и при неверном пароле, и при несуществующем email. Rate limit —
  5 попыток / 15 мин на пару email+IP (in-memory, см. `app/services/rate_limit.py`).
- `POST /api/v1/auth/password/forgot` `{email}` → **всегда `200`** с одинаковым телом
  (нельзя перебором узнать зарегистрированные email). Генерирует одноразовый токен (TTL 45 мин),
  в БД кладёт только его sha256-хеш, шлёт письмо со ссылкой. Отдельный rate limit: 3/час на
  email + 10/час на IP.
- `POST /api/v1/auth/password/reset` `{token, new_password}` → токен одноразовый (гасится сразу),
  явный `400 INVALID_OR_EXPIRED_TOKEN` при истёкшем/неверном/использованном.

Пароли: `passlib[bcrypt]` (`app/services/passwords.py`), длина 8–72 (72 — предел bcrypt).
Коды ошибок — `docs/API_ERRORS.md`.

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
  - режим `gibdd_exam`: при ошибке в **основном** вопросе подмешиваются +5 доп. вопросов из того
    же `topic_id` (лимит: 2 ошибки / 10 доп. вопросов). **Ошибка в дополнительном вопросе
    (`is_extra`) сразу завершает экзамен как несданный** (`session_finished_forced: true`,
    `exam_passed = false`); после этого `/answer` отдаёт `409 SESSION_ALREADY_FINISHED`.
- `POST /api/v1/tickets/session/finish` — завершение сессии, фиксация `correct_count` / `errors_count`,
  для `gibdd_exam` — `passed`: берётся из `test_sessions.exam_passed`, если вердикт уже вынесен
  (форс-провал), иначе `errors_count <= EXAM_MAX_ERRORS_ALLOWED`.

### 3a. Прогресс
`GET /api/v1/progress` — прогресс пользователя, посчитанный на бэкенде (не сбрасывается при
перезагрузке фронта):
- `tickets[]` — статус каждого билета A_B: `not_started` / `in_progress` (начат, не завершён) /
  `passed` (хотя бы раз завершён без ошибок → зелёный) / `failed` (завершался только с ошибками
  → красный). Считается из `test_sessions` режима `theory`, отдельной таблицы прогресса нет.
- `topics[]` — по теме: `questions_passed` из `questions_total` (сколько разных вопросов темы
  хотя бы раз решены верно).
- `bank` — то же по всему банку A_B (для виджета «Прогресс»): только верно решённые уникальные
  вопросы, а не все отвеченные.

### 4. Жизни (Freemium)
Free: `lives_current = lives_max = 10` по умолчанию. Списание — 1 жизнь за неверный ответ.
Лимит хранится в `users.lives_max` (не в константе), чтобы менять под акции без релиза.
При `lives_current == 0` и `is_premium == False` — `403 OUT_OF_LIVES` на старте новой сессии.
Premium — не ограничены.

**Восстановление — модель ТЗ v1.5 §4.7: «+1 жизнь через `LIVES_REGEN_HOURS` (24) ч с момента,
когда жизни опустились ниже максимума».**
- `users.lives_regen_at` — момент начисления следующей +1 жизни; `NULL` = жизни на максимуме.
  Ставится при первом падении ниже `lives_max`, сдвигается на +24 ч после каждого начисления,
  обнуляется при достижении `lives_max`.
- Начисление **ленивое** — `services/lives.apply_lives_regen()` вызывается в `get_current_user`
  при каждом запросе (догоняет сразу за все прошедшие 24-часовые интервалы). Джоба
  `app/workers/lives_reset.py::regen_free_users_lives` (раз в час) — только подстраховка для
  тех, кто давно не заходил.
- `GET /api/v1/users/me` отдаёт `lives_regen_at` (когда придёт следующая жизнь; `null` для
  Premium / полного запаса) и `lives_reset_at` (когда жизни начислялись в последний раз) —
  для таймера восстановления в ЛК и на дашборде.

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
  оплаченного периода. `404 SUBSCRIPTION_NOT_FOUND`, если подписки нет.
- `GET /api/v1/subscriptions/me` — подписка пользователя либо **`200 null`** (не `404`), если
  Premium ни разу не покупался: для Free это ожидаемое состояние, а не ошибка — так в консоли
  браузера не мигает «Failed to load resource: 404».

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
   - **SMTP (сброс пароля)**: если `SMTP_HOST` пуст — письма только пишутся в лог backend'а
     (заглушка, как `OAUTH_ALLOW_MOCK`). **Перед продакшеном обязателен реальный SMTP-провайдер
     с настроенными SPF/DKIM/DMARC для домена `SMTP_FROM`** — иначе письма сброса пароля уйдут
     в спам или будут отклонены. Также задать `FRONTEND_PASSWORD_RESET_URL` на реальную
     страницу фронтенда.
   - Rate limit входа/сброса пароля — **in-memory, на один процесс** (`app/services/rate_limit.py`):
     при нескольких uvicorn-воркерах у каждого свой счётчик, при рестарте счётчики обнуляются.
     Для prod под нагрузкой — вынести в Redis (ключи те же).
2. `docker compose up -d --build` — миграции Alembic (включая `0007_email_password_auth`)
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

**Auth — отложено в Фазу 2:** обязательная верификация email (эндпоинт `POST /auth/email/verify`
+ gate на `email_verified_at`), связывание нескольких способов входа с одним аккаунтом
(`POST /auth/link/...`). Таблица `auth_identities` и колонка `email_verified_at` уже рассчитаны
на «несколько identity у одного пользователя», API-контракт `TokenResponse` от способа входа
не зависит.

## Известные точки для доработки перед продакшеном

1. Проверка подписи вебхука эквайринга (сейчас — TODO, любой POST на `/billing/webhook`
   с валидным `metadata.user_id` считается доверенным).
2. Реальные ключи `ACQUIRER_SHOP_ID` / `ACQUIRER_SECRET_KEY` — без них `checkout/init` возвращает
   мок-ссылку для локальной разработки.
3. Rate limiting на `auth`/`billing` эндпоинты.
4. Идемпотентность вебхука по `external_payment_id` (сейчас уникальный индекс защищает от дублей
   на уровне БД, но повторная доставка вебхука не возвращает отдельный флаг "already processed").
