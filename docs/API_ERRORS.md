# Справочник кодов ошибок API

Все ошибки API возвращаются в формате `{"detail": "КОД_ОШИБКИ"}` (кроме 422 — это стандартная
валидация FastAPI/Pydantic со своей структурой `{"detail": [...]}`, см. `HTTPValidationError`
в Swagger). Самые частые коды продублированы прямо в Swagger в описании `responses` под каждым
эндпоинтом — здесь полный список для справки.

## Аутентификация (401) — применимо ко ВСЕМ защищённым эндпоинтам

Любой эндпоинт с `security: [{"HTTPBearer": []}]` в Swagger может вернуть один из этих кодов,
если JWT отсутствует / истёк / указывает на несуществующего пользователя. Не документируется
отдельно под каждым эндпоинтом в Swagger, т.к. это общее поведение зависимости `get_current_user`.

| Код | Когда |
|---|---|
| `NOT_AUTHENTICATED` | Заголовок `Authorization: Bearer <token>` вообще не передан |
| `INVALID_TOKEN` | Токен просрочен, повреждён или подписан другим секретом |
| `USER_NOT_FOUND` | Токен валиден, но пользователь с таким id удалён из БД |

## `POST /api/v1/auth/oauth/{provider}`

| Код | HTTP | Когда |
|---|---|---|
| `OAUTH_EXCHANGE_FAILED` | 400 | Провайдер (Yandex/VK) отклонил `code` — истёк, уже использован, неверный `redirect_uri` |
| `UNSUPPORTED_PROVIDER` | 400 | Практически недостижимо — `provider` уже валидируется как enum на уровне пути |

## `POST /api/v1/auth/register`

| Код | HTTP | Когда |
|---|---|---|
| `EMAIL_ALREADY_REGISTERED` | 409 | Этот email уже привязан к входу по паролю (`auth_identities.type='password'`). Сравнение регистронезависимое |
| `VALIDATION_ERROR` | 422 | Невалидный email, пароль < 8 или > 72 символов, пустое имя |

## `POST /api/v1/auth/login`

| Код | HTTP | Когда |
|---|---|---|
| `INVALID_CREDENTIALS` | 401 | Неверный пароль **или** несуществующий email — намеренно один код, чтобы не раскрывать, какой из двух |
| `RATE_LIMITED` | 429 | Больше `LOGIN_RATE_MAX_ATTEMPTS` (5) попыток за `LOGIN_RATE_WINDOW_MINUTES` (15) на пару email+IP |

## `POST /api/v1/auth/password/forgot`

Всегда `200` с одинаковым нейтральным телом (`{"detail": "Если такой email зарегистрирован…"}`)
— по ответу нельзя определить, существует ли email. Единственное исключение:

| Код | HTTP | Когда |
|---|---|---|
| `RATE_LIMITED` | 429 | Больше `PASSWORD_FORGOT_RATE_MAX_PER_EMAIL` (3) запросов на один email или `…_PER_IP` (10) с одного IP за `…_WINDOW_MINUTES` (60). 429 не зависит от существования email, поэтому не раскрывает его |

## `POST /api/v1/auth/password/reset`

| Код | HTTP | Когда |
|---|---|---|
| `INVALID_OR_EXPIRED_TOKEN` | 400 | Токен неизвестен, истёк (TTL `PASSWORD_RESET_TOKEN_TTL_MINUTES`) или уже был использован (одноразовый) |
| `VALIDATION_ERROR` | 422 | `new_password` < 8 или > 72 символов |

## Связывание способов входа (`/api/v1/auth/identities*`) — все требуют `Authorization: Bearer`

`GET /api/v1/auth/identities` — ошибок, кроме общих 401, не возвращает.

### `POST /api/v1/auth/identities/oauth/{provider}`

| Код | HTTP | Когда |
|---|---|---|
| `OAUTH_EXCHANGE_FAILED` | 400 | Провайдер отклонил `code` |
| `IDENTITY_ALREADY_LINKED` | 409 | Этот аккаунт Yandex/VK уже привязан к ДРУГОМУ `users.id` — молча не перепривязываем |

(Если тот же аккаунт провайдера уже привязан к ЭТОМУ же пользователю — `200`, идемпотентно, список identities без изменений.)

### `POST /api/v1/auth/identities/password`

| Код | HTTP | Когда |
|---|---|---|
| `PASSWORD_ALREADY_SET` | 409 | У текущего пользователя уже есть вход по паролю — нужна отдельная смена пароля, не эта ручка |
| `EMAIL_ALREADY_REGISTERED` | 409 | Этот email уже занят входом по паролю у другого пользователя (та же проверка, что в `/auth/register`) |
| `VALIDATION_ERROR` | 422 | Невалидный email / пароль < 8 или > 72 |

### `DELETE /api/v1/auth/identities/{type}`

| Код | HTTP | Когда |
|---|---|---|
| `CANNOT_UNLINK_LAST_IDENTITY` | 409 | Это единственный оставшийся способ входа — иначе аккаунт стал бы навсегда недоступен |
| `IDENTITY_NOT_FOUND` | 404 | У пользователя нет привязанного способа входа этого типа |
| `VALIDATION_ERROR` | 422 | `{type}` не входит в `password` \| `yandex` \| `vk` |

## `POST /api/v1/tickets/session/start`

| Код | HTTP | Когда |
|---|---|---|
| `OUT_OF_LIVES` | 403 | У Free-пользователя `lives_current == 0` |
| `NO_QUESTIONS_FOUND` | 404 | По `ticket_id`/`topic_id` нет вопросов, либо пусто в "Ошибках"/"Избранном" для этого режима |

## `POST /api/v1/tickets/session/answer`

| Код | HTTP | Когда |
|---|---|---|
| `SESSION_NOT_FOUND` | 404 | `session_id` не существует или принадлежит другому пользователю |
| `QUESTION_NOT_IN_SESSION` | 404 | `question_id` не входит в состав этой сессии |
| `QUESTION_NOT_FOUND` | 404 | Сам вопрос не найден (не должно происходить при валидных данных) |
| `SESSION_ALREADY_FINISHED` | 409 | Сессия уже завершена — ответы больше не принимаются. В `gibdd_exam` — в т.ч. после форс-завершения (ошибка в доп. вопросе / превышен лимит ошибок): клиент должен вызвать `/finish` за итогом |
| `QUESTION_ALREADY_ANSWERED` | 409 | На этот вопрос в этой сессии уже отвечали |
| `INVALID_ANSWER` | 400 | `answer_id` не относится к переданному `question_id` |

## `POST /api/v1/tickets/session/finish`

| Код | HTTP | Когда |
|---|---|---|
| `SESSION_NOT_FOUND` | 404 | См. выше |
| `SESSION_ALREADY_FINISHED` | 409 | Повторный вызов `/finish` для уже завершённой сессии |

## `GET /api/v1/questions/{id}/image`

| Код | HTTP | Когда |
|---|---|---|
| `IMAGE_NOT_FOUND` | 404 | У вопроса нет картинки, либо вопрос с таким id не существует |

## `POST /api/v1/questions/{id}/favorite`

| Код | HTTP | Когда |
|---|---|---|
| `QUESTION_NOT_FOUND` | 404 | Вопрос с таким id не существует |

(У `DELETE .../favorite` намеренно нет 404 — удаление того, чего не было в избранном, тихо
считается успехом: `is_favorite: false` в ответе в обоих случаях.)

## `GET /api/v1/subscriptions/me`

Ошибок «нет подписки» не возвращает: для Free-пользователя без Premium отвечает `200` с телом
`null` (ожидаемое состояние, а не ошибка — чтобы в консоли браузера не мигало «404»).

## `POST /api/v1/subscriptions/cancel`

| Код | HTTP | Когда |
|---|---|---|
| `SUBSCRIPTION_NOT_FOUND` | 404 | Пользователь Free и никогда не покупал Premium |

## `POST /api/v1/billing/webhook`

Эти коды видит эквайринг (ЮKassa/Т-Банк), не фронтенд — но для полноты:

| Код | HTTP | Когда |
|---|---|---|
| `MISSING_USER_ID_IN_METADATA` | 400 | В вебхуке нет `metadata.user_id` |
| `INVALID_USER_ID` | 400 | `metadata.user_id` не парсится как UUID |
| `USER_NOT_FOUND` | 404 | Пользователь с таким id не существует |
