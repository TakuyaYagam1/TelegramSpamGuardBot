# TelegramSpamGuardBot

Telegram-бот для защиты групп и топиков от спама. Бот проверяет новых участников, удаляет неподтвержденных пользователей, анализирует сообщения по стоп-словам и при необходимости уточняет решение через LLM.

## Возможности

- Верификация новых участников через Telegram join request и приватную кнопку.
- До прохождения проверки пользователь не попадает в группу, не читает чат и не пишет сообщения.
- Таймаут подтверждения: 3 минуты.
- Корректная работа в Telegram-топиках через `message_thread_id`.
- Быстрая проверка сообщений по стоп-словам.
- Дополнительная LLM-проверка подозрительных сообщений.
- Flood-защита: одинаковый текст, стикер или медиа подряд удаляются с предупреждением, а повтор после предупреждения приводит к исключению.
- Два режима реакции на спам:
  - `delete`: удалить сообщение и заблокировать пользователя;
  - `notify_admin`: уведомить администратора.
- Логирование действий бота.
- Если пользователь не прошел проверку за 3 минуты, бот отклоняет заявку или кикает пользователя из группы.
- Redis для временного состояния верификации и служебных данных.

## Системный дизайн

```text
Telegram join request
        |
        | long polling
        v
Telegram bot container
  Python + aiogram
        |
        | private challenge, pending verification, TTL, flags
        v
Redis container

Spam flow:
message -> duplicate flood check -> stop words -> LLM check -> delete / notify admin -> log
```

Для v1 используется long polling: приложению не нужен публичный HTTP-порт, домен или TLS. Redis работает только во внутренней Docker Compose-сети и не публикуется наружу.

## Структура проекта

```text
pyproject.toml             # метаданные проекта, зависимости, настройки Ruff/Pytest
app/
  __main__.py              # точка входа пакета: python -m app
  bootstrap/
    application.py         # composition root и DI-сборка приложения
    command.py             # регистрация команд в меню Telegram
    lifecycle.py           # startup/shutdown хуки
    verification_restore.py # helpers восстановления pending verification
    verification_timer.py  # восстановление таймеров pending verification
  config/
    settings.py            # pydantic-settings и .env
  domain/
    moderation.py          # enum'ы модерации
    spam.py                # value objects spam detection
    stopword.py            # доменные правила stop-word
    verification.py        # value objects верификации
    data/
      stopword/            # словари stop-word
  usecase/
    contract.py            # Protocol-порты для зависимостей usecase-слоя
    moderation/
      action.py            # фасад ModerationService для delete / notify / warn / ban
      auto_delete.py       # durable cleanup временных Telegram-сообщений
      flood_action.py      # duplicate flood warning / cleanup / kick actions
      message.py           # форматирование moderation-сообщений и лог-текста
      notification.py      # выбор и доставка admin notification
      spam_action.py       # delete / notify actions для confirmed spam
      spam_detector.py     # stop-word + LLM decision flow
      stop_word_action.py  # Telegram-actions для stop-word warning
      warning_action.py    # stop-word warning и cleanup warning-сообщений
    verification/
      approval.py          # approval flow верификации
      challenge.py         # отправка verification challenge
      flow.py              # старт и cleanup верификации
      message.py           # тексты верификации и callback payloads
      permission.py        # Telegram permissions для unverified/verified users
      task.py              # registry задач таймеров верификации
      timeout.py           # timeout и cleanup flow верификации
  infrastructure/
    llm/
      client.py            # фасад LLM-клиента
      prompt.py            # сборка LLM-промптов
    redis/
      client.py            # lifecycle Redis-клиента
      repository/          # Redis-реализации repository-портов
  bot/                     # Telegram transport layer: controller, keyboard и middleware
    controller/
      v1/                  # Telegram transport controller версии v1
        admin/             # команды, callbacks, permissions и panel админа
          argument.py
          callback.py
          command.py
          panel.py
          permission.py
          router.py
        moderation/
          action.py
          flood.py
          message.py
          router.py
        user.py
        verification.py
    keyboard/              # сборка reply/inline UI Telegram
    middleware/            # aiogram middleware и Redis DI
    state/                 # FSM extension points
    util/                  # Telegram-тексты и helpers
```

`bot/controller/v1/` здесь выполняет роль transport controller для Telegram updates: принимает update, проверяет transport-specific поля и вызывает usecase. Бизнес-правила верификации, spam detection и moderation actions живут вне Telegram-слоя. Это держит тесты сфокусированными и позволяет заменить transport layer без переписывания core behavior.

Usecase-слой зависит от `Protocol`-портов из `app/usecase/contract.py`, а не от конкретных Redis/LLM-реализаций. Реализации этих портов лежат в `app/infrastructure`: например, `app/infrastructure/redis/repository/` означает не абстрактный repository-слой внутри Redis, а конкретные Redis-backed adapters для usecase-контрактов.

PostgreSQL, Alembic, `app/database/` и `migrations/` намеренно не добавлены в v1: текущие требования используют Redis-only storage. Реляционный слой стоит добавлять только тогда, когда появятся постоянные relational data.

## Хранилище и LLM

Бот не использует базу данных. Все служебное состояние хранится в Redis:

- `verify:{chat_id}:{user_id}` - pending verification с TTL, id приватного challenge-сообщения, `verification_chat_id`, `message_thread_id` для legacy-записей и временем создания;
- `verified:{chat_id}:{user_id}` - отметка, что пользователь прошел верификацию;
- `duplicate_message:{chat_id}:{user_id}` - текущая серия одинаковых сообщений пользователя с TTL;
- `duplicate_message_warning:{chat_id}:{user_id}` - digest flood-сообщения, за которое пользователь уже получил предупреждение;
- `duplicate_message_warning_grace:{chat_id}:{user_id}` - короткое окно после предупреждения, в котором повторы удаляются без kick;
- `stop_word_warning:{chat_id}:{user_id}` - факт первого предупреждения за stop-word spam с TTL;
- `auto_delete_message:{chat_id}:{message_id}` - pending cleanup временного warning-сообщения бота с TTL;
- `llm:{sha256}` - кеш ответа LLM на нормализованный текст сообщения с TTL из `LLM_CACHE_TTL_SECONDS`.

При старте приложение выполняет `PING` Redis, восстанавливает таймеры для активных `verify:*` ключей и задачи удаления временных `auto_delete_message:*` сообщений. Если ключ поврежден или не имеет TTL, он безопасно удаляется и событие пишется в лог. Восстановленный timeout для join request отклоняет заявку и банит пользователя.

## UX верификации

Для полного сценария защиты группа должна использовать заявки на вступление: включите approve новых участников в настройках группы или создайте invite link с join request. В этом режиме пользователь сначала отправляет заявку, но еще не становится участником группы.

Бот получает `chat_join_request`, отправляет пользователю приватное сообщение с предупреждением `⚠️` и кнопкой `✅ Я человек`, затем ждет до `VERIFY_TIMEOUT_SECONDS`, по умолчанию 180 секунд. Пока пользователь не нажал кнопку, Telegram не дает ему читать чат и отправлять сообщения, потому что заявка еще не одобрена.

После нажатия кнопки бот вызывает `approve_chat_join_request`, удаляет приватное challenge-сообщение, отправляет личное `✅ Готово, доступ открыт`, отмечает пользователя как verified и очищает pending-запись. Если timeout истек, бот отправляет личное `❌ Проверка не пройдена`, вызывает `decline_chat_join_request`, `ban_chat_member` и удаляет pending-запись.

LLM-интеграция работает через OpenAI-compatible `/chat/completions`: задаются `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` и timeout. В обычном spam-flow LLM вызывается только после совпадения stop-word, а ответ кешируется на `LLM_CACHE_TTL_SECONDS`, по умолчанию 300 секунд. Первое confirmed stop-word spam-сообщение удаляется без kick: бот отправляет предупреждение `⚠️ Слово или фраза «казино» запрещены в чате. В следующий раз вы будете исключены из группы`, а само предупреждение удаляется через `STOP_WORD_WARNING_MESSAGE_TTL_SECONDS`. Повторное stop-word spam-сообщение в течение `STOP_WORD_WARNING_TTL_SECONDS` идет в обычный `ACTION_MODE`: в `delete` режиме пользователь будет исключен через ban/unban, в `notify_admin` режиме администратор получит уведомление. Для файлов без текста бот проверяет доступные метаданные: `file_name`, `mime_type`, emoji/set name стикера и caption. Отдельно бот детерминированно отслеживает одинаковые сообщения подряд: текст сравнивается по нормализованной строке, стикеры и медиа - по `file_unique_id`. При достижении `DUPLICATE_MESSAGE_WARN_THRESHOLD` бот удаляет накопленные дубли и предупреждает пользователя. Warning ставится атомарно и не дублируется при параллельной обработке сообщений. В течение `DUPLICATE_MESSAGE_KICK_GRACE_SECONDS`, по умолчанию 3 секунды, после предупреждения новые серии дублей удаляются без kick, чтобы пользователь успел заметить предупреждение. После grace-window повторный duplicate-flood в пределах `DUPLICATE_MESSAGE_WARNING_TTL_SECONDS` приводит к kick через ban/unban. Ответы LLM `да/yes` считаются спамом, `нет/no` - не спамом; при timeout, ошибке или непонятном ответе обычный stop-word flow применяет fallback на ключевые слова.

## Словари stop-words

Базовые spam-маркеры вынесены из Python-кода в packaged data:

- `app/domain/data/stopword/spam_ru.txt` - русские фразы;
- `app/domain/data/stopword/spam_en.txt` - английские фразы.

Формат простой: один термин или фраза на строку. Пустые строки и строки с `#` игнорируются, дубли убираются регистронезависимо. После изменения словарей достаточно пересобрать контейнер: `docker compose up -d --build`.

Внешние profanity-листы можно импортировать позже отдельной задачей, но их нельзя слепо смешивать с текущими spam-словами. Такие списки чаще ловят мат и оскорбления, а не рекламу казино, крипты, займов и мошеннических ссылок. Перед импортом нужно проверить лицензию, язык, качество терминов и риск ложных срабатываний.

## Стек

- Python: `python:3.14.5-slim-trixie`
- Telegram framework: `aiogram 3.28.2`
- Cache/state storage: `redis:8.8.0-alpine3.23`
- Runtime: Docker Compose
- CI: GitHub Actions, pytest `9.0.3`, mypy `2.1.0`, Ruff `0.15.15`, Docker Buildx

Python-зависимости зафиксированы как latest stable на момент обновления: прямые зависимости указаны exact-версиями в `pyproject.toml`, а транзитивные зависимости закреплены в `requirements.lock`. Docker, Makefile и CI ставят зависимости через `-c requirements.lock`, поэтому один и тот же commit собирает один и тот же dependency graph.

## Быстрый старт

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

То же через Makefile:

```bash
make env-init
make install
make up
make logs-bot
```

Проверить состояние:

```bash
docker compose ps
docker compose logs -f bot
```

## Makefile

Основные команды для разработки и деплоя:

```bash
make help          # список команд
make install       # установка зависимостей .[dev]
make test          # pytest -q
make lint          # ruff check
make fmt           # ruff format
make typecheck     # mypy app
make check         # lint + format check + typecheck + tests + compileall + compose config
make check-ci      # то же для CI, но с pytest-results.xml
make up            # docker compose up -d --build
make up-bot        # пересобрать и перезапустить только bot
make logs-bot      # логи bot
make redis-cli     # redis-cli внутри контейнера
make spam-log      # tail /app/logs/spam.log внутри bot
make clean         # удалить локальные cache-файлы
```

Остановить:

```bash
docker compose down
```

## Переменные окружения

Основные переменные задаются в `.env`:

```env
BOT_TOKEN=...
TELEGRAM_PROXY_URL=
REDIS_URL=redis://redis:6379/0
VERIFY_TIMEOUT_SECONDS=180
DUPLICATE_MESSAGE_WINDOW_SECONDS=60
DUPLICATE_MESSAGE_WARN_THRESHOLD=3
DUPLICATE_MESSAGE_WARNING_TTL_SECONDS=300
DUPLICATE_MESSAGE_KICK_GRACE_SECONDS=3
DUPLICATE_WARNING_MESSAGE_TTL_SECONDS=60
STOP_WORD_WARNING_TTL_SECONDS=300
STOP_WORD_WARNING_MESSAGE_TTL_SECONDS=60
AUTO_DELETE_MESSAGE_CLEANUP_GRACE_SECONDS=86400
ACTION_MODE=notify_admin
ADMIN_USERNAME=@admin
ADMIN_ID=
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_MODEL=...
LLM_TIMEOUT_SECONDS=8
LLM_CACHE_TTL_SECONDS=300
LOG_LEVEL=INFO
LOG_FILE=/app/logs/spam.log
```

Назначение переменных:

- `BOT_TOKEN` - токен Telegram-бота из BotFather.
- `REDIS_URL` - адрес Redis внутри Compose-сети.
- `VERIFY_TIMEOUT_SECONDS` - время ожидания верификации нового пользователя.
- `DUPLICATE_MESSAGE_WINDOW_SECONDS` - окно, в котором считаются одинаковые сообщения подряд от одного пользователя.
- `DUPLICATE_MESSAGE_WARN_THRESHOLD` - сколько одинаковых сообщений подряд нужно для удаления дублей и предупреждения.
- `DUPLICATE_MESSAGE_WARNING_TTL_SECONDS` - сколько действует предупреждение перед kick при новом таком же повторе.
- `DUPLICATE_MESSAGE_KICK_GRACE_SECONDS` - сколько секунд после первого предупреждения удалять повторный flood без kick, по умолчанию 3.
- `DUPLICATE_WARNING_MESSAGE_TTL_SECONDS` - через сколько секунд удалить warning-сообщение бота из чата.
- `STOP_WORD_WARNING_TTL_SECONDS` - сколько действует первое предупреждение за stop-word spam.
- `STOP_WORD_WARNING_MESSAGE_TTL_SECONDS` - через сколько секунд удалить warning-сообщение за stop-word spam.
- `AUTO_DELETE_MESSAGE_CLEANUP_GRACE_SECONDS` - сколько дополнительно хранить pending cleanup warning-сообщений в Redis, чтобы бот мог удалить их после рестарта.
- `ACTION_MODE` - реакция на спам: `delete` или `notify_admin`.
- `ADMIN_USERNAME` / `ADMIN_ID` - fallback-получатель уведомлений для `notify_admin`.
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS` - параметры OpenAI-compatible LLM provider.
- `LLM_CACHE_TTL_SECONDS` - сколько хранить ответ LLM для одного текста, по умолчанию 300 секунд.
- `LOG_LEVEL` и `LOG_FILE` - уровень логирования и путь к `spam.log`.

`ACTION_MODE` принимает значения:

- `delete`: удалить спам-сообщение и заблокировать пользователя;
- `notify_admin`: отправить уведомление администратору.

Режим можно переключать без изменения `.env` и без рестарта контейнера. Реальный администратор Telegram-чата может открыть панель командой `/admin` или `/help`, а затем выбрать режим inline-кнопками `Удалять спам`, `Только уведомлять` или `Сбросить к env`. Если команда вызвана в группе, бот удаляет команду из чата и отправляет админ-панель в ЛС администратору. Для этого администратор должен заранее открыть личный чат с ботом через `/start`. `ADMIN_ID` и `ADMIN_USERNAME` используются как fallback для личных команд и дефолтного получателя уведомлений.

Также доступны текстовые команды:

```text
/admin
/help
/mode
/mode delete
/mode notify_admin
/mode reset
/notify
/notify me
/notify @username
/notify 123456789
/notify reset
```

В меню Telegram `/` бот программно регистрирует только `/admin`, `/help`, `/mode` и `/notify` при старте через `bot.set_my_commands`. Для обычных участников групп и обычных личных чатов меню очищается, а команды показываются через `BotCommandScopeAllChatAdministrators` и персональный scope для `ADMIN_ID`. Аргументы вроде `/mode delete` и `/notify me` показываются внутри `/admin`, потому что Telegram command menu хранит только название команды и короткое описание.

Значение, заданное через `/mode delete` или `/mode notify_admin`, хранится в Redis per-chat в ключе `settings:action_mode:{chat_id}` и имеет приоритет над `.env` только для конкретного чата. Старый глобальный ключ `settings:action_mode` читается как fallback для совместимости с ранними версиями. Команда `/mode reset` удаляет runtime override для текущего чата, очищает старый глобальный override и возвращает режим из `ACTION_MODE`. Получатель из `/notify ...` хранится в Redis per-chat в ключе `settings:notification_target:{chat_id}`; numeric id отправляет уведомления в ЛС, `@username` оставляет уведомление в чате с mention.

## Запуск на сервере

На сервере должны быть установлены Docker и Docker Compose.

```bash
git clone <repo-url> TelegramSpamGuardBot
cd TelegramSpamGuardBot
cp .env.example .env
nano .env
docker compose up -d --build
```

Обновление:

```bash
git pull
docker compose up -d --build
docker compose ps
```

Адрес сервера, токены и реальные ключи не хранятся в репозитории.

Логи:

```bash
docker compose logs -f bot
docker compose exec bot sh -lc 'tail -f /app/logs/spam.log'
```

`spam.log` содержит структурированные события верификации, timeout-удаления, спам-детекта, действий модерации и безопасно отредактированные ошибки Telegram API.

## CI/CD

В репозитории настроен CI для проверки инфраструктуры и контейнерной сборки.

CI выполняет `make check-ci ENV_FILE=.env.example`, поэтому локальные проверки и GitHub Actions используют один набор команд.

CI проверяет:

- запуск на каждом `push` в любую ветку, на pull request и вручную через `workflow_dispatch`;
- выгрузку `pytest-results.xml` в артефакты workflow;
- lint через Ruff;
- проверку форматирования через Ruff;
- статическую проверку типов через mypy;
- проверку обязательных файлов;
- валидацию `docker compose config`;
- сборку Docker-образа через Buildx;
- запуск Redis;
- проверку Redis через `redis-cli ping`.

Сборка использует GitHub Actions cache:

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

Деплой выполняется вручную через `git pull` и `docker compose up -d --build`.

## Безопасность

- `.env` не коммитится.
- Redis не публикуется наружу.
- Бот должен быть администратором группы с правами на обработку заявок на вступление и ban пользователей: это требуется для приватной join-request верификации.
- Для `ACTION_MODE=delete` боту также нужны права на удаление сообщений и ban/unban пользователей.
- Контейнер бота запускается от non-root пользователя.
- Для контейнера включен `no-new-privileges`.
- Секреты хранятся только на сервере или в GitHub Secrets для CI/CD.
