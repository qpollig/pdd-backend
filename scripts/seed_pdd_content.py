"""
Наполняет БД (topics/tickets/questions/answers) контентом из открытого репозитория
https://github.com/etspring/pdd_russia

Как это устроено:
1. Один запрос к GitHub Trees API на КАЖДУЮ категорию — получаем список файлов репозитория.
2. Отбираем все .json файлы под questions/{category}/ (category = A_B и/или C_D).
3. Скачиваем каждый файл (raw.githubusercontent.com — CDN, лимит запросов GitHub API
   на него не распространяется).
4. Каждый файл может содержать как ОДИН вопрос (dict), так и МАССИВ вопросов (list) —
   скрипт понимает оба варианта, поэтому не завязан на точную файловую раскладку репозитория.
5. Дедуплицируем вопросы по полю "id" (MD5-хэш из самого репозитория) — ОТДЕЛЬНО в пределах
   каждой категории (один и тот же текст вопроса в A_B и в C_D — это разные билеты, оставляем оба).
6. Изображения скачиваются и хранятся В БД как bytea (Question.image_data), а не ссылкой.
   Одна и та же картинка может использоваться в нескольких вопросах — скачиваем каждую
   уникальную картинку только один раз (кэш по пути в репозитории).
7. Пишем в БД: Topic (первая тема из списка "topic" в вопросе, общая для всех категорий),
   Ticket (номер + category, парсится из "ticket_number"/"ticket_category"), Question, Answer.

Запуск (из корня проекта pdd_backend, с активным venv и настроенным .env):

    python -m scripts.seed_pdd_content

По умолчанию загружаются ОБЕ категории (A_B и C_D) — теперь это безопасно, т.к. Ticket
уникален по паре (number, category), а не по одному number.

Полезные флаги:

    python -m scripts.seed_pdd_content --category A_B     # только одна категория
    python -m scripts.seed_pdd_content --reset             # ОЧИСТИТЬ существующий контент перед импортом
    python -m scripts.seed_pdd_content --limit 20           # первые 20 файлов НА КАЖДУЮ категорию (для теста)
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx

# Чтобы можно было запускать и как `python -m scripts.seed_pdd_content`,
# и напрямую как `python scripts/seed_pdd_content.py` из корня проекта.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.content import Answer, Question, Ticket, TicketCategory, Topic  # noqa: E402

REPO_OWNER = "etspring"
REPO_NAME = "pdd_russia"
REPO_BRANCH = "master"
TREE_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/{REPO_BRANCH}?recursive=1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}/"

DOWNLOAD_CONCURRENCY = 10
FALLBACK_TOPIC_TITLE = "Без темы"

CONTENT_TYPE_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def parse_ticket_number(raw: str | None) -> int | None:
    """'Билет 2' -> 2. Возвращает None, если распарсить не удалось."""
    if not raw:
        return None
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None


def guess_content_type(path: str) -> str:
    return CONTENT_TYPE_BY_EXT.get(Path(path).suffix.lower(), "application/octet-stream")


def is_placeholder_image(image: str | None) -> bool:
    """no_image.jpg — заглушка репозитория, которую его README прямо просит добавить
    самостоятельно ('добавьте по вкусу') — то есть физически в репозитории её нет."""
    return bool(image) and Path(image).name == "no_image.jpg"


def normalize_payload_to_questions(payload) -> list[dict]:
    """Файл репозитория — либо один вопрос (dict), либо список вопросов (list)."""
    if isinstance(payload, list):
        return [q for q in payload if isinstance(q, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


async def fetch_tree_paths(client: httpx.AsyncClient, category: str) -> list[str]:
    print(f"Запрашиваю дерево файлов репозитория {REPO_OWNER}/{REPO_NAME}@{REPO_BRANCH}...")
    resp = await client.get(TREE_API_URL, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()

    if data.get("truncated"):
        print(
            "ВНИМАНИЕ: GitHub вернул усечённое дерево (truncated=true) — "
            "часть файлов могла быть пропущена. Это ограничение GitHub API на очень больших репозиториях."
        )

    prefix = f"questions/{category}/"
    paths = [
        item["path"]
        for item in data.get("tree", [])
        if item.get("type") == "blob" and item["path"].startswith(prefix) and item["path"].endswith(".json")
    ]
    return paths


async def download_questions_for_category(
    client: httpx.AsyncClient, category: str, limit: int | None
) -> list[dict]:
    paths = await fetch_tree_paths(client, category)
    if not paths:
        raise SystemExit(
            f"Не найдено ни одного .json файла под questions/{category}/ — "
            "возможно, структура репозитория изменилась. Проверьте вручную на GitHub."
        )
    if limit:
        paths = paths[:limit]

    print(f"[{category}] файлов для загрузки: {len(paths)}")

    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    results: list[list[dict]] = [[] for _ in paths]

    async def worker(index: int, path: str) -> None:
        async with semaphore:
            try:
                resp = await client.get(RAW_BASE + path, timeout=20.0)
                resp.raise_for_status()
                results[index] = normalize_payload_to_questions(resp.json())
            except Exception as exc:  # noqa: BLE001 - пропускаем проблемный файл и продолжаем импорт
                print(f"  пропуск {path}: {exc}")

    await asyncio.gather(*(worker(i, p) for i, p in enumerate(paths)))

    questions: list[dict] = []
    seen_ids: set[str] = set()  # дедуп ТОЛЬКО в пределах этой категории
    for file_questions in results:
        for q in file_questions:
            qid = q.get("id")
            if qid and qid in seen_ids:
                continue
            if qid:
                seen_ids.add(qid)
            q["_category"] = category
            questions.append(q)

    print(f"[{category}] уникальных вопросов: {len(questions)}")
    return questions


async def download_images(client: httpx.AsyncClient, image_paths: set[str]) -> dict[str, tuple[bytes, str]]:
    """Скачивает каждую уникальную картинку один раз. Возвращает {путь: (байты, content_type)}."""
    if not image_paths:
        return {}

    print(f"Уникальных картинок к скачиванию: {len(image_paths)}")
    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    cache: dict[str, tuple[bytes, str]] = {}
    lock = asyncio.Lock()
    done_counter = {"n": 0}

    async def worker(path: str) -> None:
        async with semaphore:
            try:
                resp = await client.get(RAW_BASE + path.lstrip("./"), timeout=30.0)
                resp.raise_for_status()
                async with lock:
                    cache[path] = (resp.content, guess_content_type(path))
            except Exception as exc:  # noqa: BLE001 - без картинки вопрос всё равно валиден
                print(f"  пропуск картинки {path}: {exc}")
            finally:
                async with lock:
                    done_counter["n"] += 1
                    if done_counter["n"] % 100 == 0:
                        print(f"  ...скачано картинок: {done_counter['n']}/{len(image_paths)}")

    await asyncio.gather(*(worker(p) for p in image_paths))
    print(f"Успешно скачано картинок: {len(cache)}/{len(image_paths)}")
    return cache


async def reset_content_tables() -> None:
    print("Очищаю существующий контент (TRUNCATE ... CASCADE)...")
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE session_questions, test_sessions, user_errors, "
                "answers, questions, tickets, topics CASCADE"
            )
        )
        await session.commit()


async def seed(categories: list[str], do_reset: bool, limit: int | None) -> None:
    if do_reset:
        await reset_content_tables()

    all_questions: list[dict] = []
    async with httpx.AsyncClient(headers={"Accept": "application/vnd.github+json"}) as client:
        for category in categories:
            all_questions.extend(await download_questions_for_category(client, category, limit))

        if not all_questions:
            raise SystemExit("Ни одного вопроса не удалось распарсить — прерываю импорт.")

        image_paths = {
            q["image"]
            for q in all_questions
            if q.get("image") and not is_placeholder_image(q.get("image"))
        }
        image_cache = await download_images(client, image_paths)

    # --- Темы: общие для всех категорий, дедуп по названию, порядок — по первому появлению ---
    topic_order: dict[str, int] = {}
    for q in all_questions:
        topics = q.get("topic") or []
        title = topics[0] if topics else FALLBACK_TOPIC_TITLE
        if title not in topic_order:
            topic_order[title] = len(topic_order)

    topics_by_title: dict[str, Topic] = {
        title: Topic(title=title, order_index=idx) for title, idx in topic_order.items()
    }
    print(f"Уникальных тем: {len(topics_by_title)}")

    # --- Билеты: ключ — (номер, категория), т.к. номера повторяются между категориями ---
    ticket_keys: set[tuple[int, str]] = set()
    for q in all_questions:
        ticket_number = parse_ticket_number(q.get("ticket_number"))
        if ticket_number is not None:
            ticket_keys.add((ticket_number, q["_category"]))

    tickets_by_key: dict[tuple[int, str], Ticket] = {
        key: Ticket(number=key[0], category=TicketCategory(key[1])) for key in sorted(ticket_keys)
    }
    print(f"Уникальных билетов (все категории): {len(tickets_by_key)}")

    # --- Вопросы и ответы ---
    ticket_question_counters: dict[tuple[int, str], int] = {}
    topic_question_counters: dict[str, int] = {}
    question_objects: list[Question] = []
    images_attached = 0

    for q in all_questions:
        topics = q.get("topic") or []
        topic_title = topics[0] if topics else FALLBACK_TOPIC_TITLE
        topic = topics_by_title[topic_title]

        category = q["_category"]
        ticket_number = parse_ticket_number(q.get("ticket_number"))
        ticket_key = (ticket_number, category) if ticket_number is not None else None
        ticket = tickets_by_key.get(ticket_key) if ticket_key else None

        if ticket_key is not None:
            order_index = ticket_question_counters.get(ticket_key, 0)
            ticket_question_counters[ticket_key] = order_index + 1
        else:
            order_index = topic_question_counters.get(topic_title, 0)
            topic_question_counters[topic_title] = order_index + 1

        image_path = q.get("image")
        image_data: bytes | None = None
        image_content_type: str | None = None
        if image_path and image_path in image_cache:
            image_data, image_content_type = image_cache[image_path]
            images_attached += 1

        question = Question(
            topic=topic,
            ticket=ticket,
            order_index=order_index,
            text=q.get("question", "").strip(),
            image_data=image_data,
            image_content_type=image_content_type,
            explanation=(q.get("answer_tip") or q.get("correct_answer") or "").strip() or None,
        )

        for a_idx, answer in enumerate(q.get("answers") or []):
            question.answers.append(
                Answer(
                    order_index=a_idx,
                    text=(answer.get("answer_text") or "").strip(),
                    is_correct=bool(answer.get("is_correct")),
                )
            )

        question_objects.append(question)

    print(f"Всего вопросов к вставке: {len(question_objects)} (с картинкой: {images_attached})")

    async with AsyncSessionLocal() as session:
        session.add_all(topics_by_title.values())
        session.add_all(tickets_by_key.values())
        session.add_all(question_objects)  # answers добавятся каскадно через relationship
        await session.commit()

    print("Готово. Контент импортирован.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--category",
        choices=["A_B", "C_D", "both"],
        default="both",
        help="Категория(и) прав для импорта. По умолчанию — обе (both).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Очистить существующий контент (topics/tickets/questions/answers и связанные "
        "тестовые сессии) перед импортом. Деструктивная операция!",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Импортировать только первые N файлов НА КАЖДУЮ категорию (для быстрой проверки).",
    )
    args = parser.parse_args()

    categories = ["A_B", "C_D"] if args.category == "both" else [args.category]
    asyncio.run(seed(categories, args.reset, args.limit))


if __name__ == "__main__":
    main()
