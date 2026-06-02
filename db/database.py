import aiosqlite

DB_PATH = "bot.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_verifications (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                message_thread_id INTEGER,
                verification_message_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
            """
        )
        await db.commit()


async def add_pending(
    user_id: int,
    chat_id: int,
    thread_id: int | None,
    msg_id: int,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO pending_verifications
                (user_id, chat_id, message_thread_id, verification_message_id)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, chat_id, thread_id, msg_id),
        )
        await db.commit()


async def get_pending(user_id: int, chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pending_verifications WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as cursor:
            return await cursor.fetchone()


async def remove_pending(user_id: int, chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM pending_verifications WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        await db.commit()
