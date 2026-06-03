"""Redis repository integration tests against a real Redis container"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer

from app.domain import ActionMode
from app.infrastructure.redis import (
    DuplicateMessageRepository,
    LLMResultCacheRepository,
    PendingVerificationRepository,
    RuntimeSettingsRepository,
    VerifiedUserRepository,
)

REDIS_IMAGE = "redis:8.8.0-alpine3.23"


@pytest.fixture(scope="module")
def redis_endpoint() -> Iterator[tuple[str, int]]:
    with RedisContainer(image=REDIS_IMAGE) as container:
        yield (
            container.get_container_host_ip(),
            int(container.get_exposed_port(6379)),
        )


def redis_client(redis_endpoint: tuple[str, int]) -> Redis:
    host, port = redis_endpoint
    return Redis(host=host, port=port, decode_responses=True)


def test_redis_repositories_persist_verification_state(
    redis_endpoint: tuple[str, int],
) -> None:
    async def run() -> None:
        redis = redis_client(redis_endpoint)
        try:
            await redis.flushdb()
            pending_repository = PendingVerificationRepository(redis, ttl_seconds=120)
            verified_repository = VerifiedUserRepository(redis)

            pending = await pending_repository.create(
                user_id=42,
                chat_id=-100123,
                verification_message_id=777,
                message_thread_id=555,
                verification_chat_id=4242,
            )

            stored = await pending_repository.get(chat_id=-100123, user_id=42)
            ttl = await pending_repository.get_ttl(chat_id=-100123, user_id=42)
            assert stored == pending
            assert ttl is not None
            assert 0 < ttl <= 120

            await verified_repository.mark_verified(chat_id=-100123, user_id=42)

            assert await verified_repository.is_verified(
                chat_id=-100123,
                user_id=42,
            )
            assert await pending_repository.delete(chat_id=-100123, user_id=42)
            assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        finally:
            await redis.aclose()

    asyncio.run(run())


def test_redis_repositories_use_real_nx_and_ttl_semantics(
    redis_endpoint: tuple[str, int],
) -> None:
    async def run() -> None:
        redis = redis_client(redis_endpoint)
        try:
            await redis.flushdb()
            repository = DuplicateMessageRepository(
                redis,
                ttl_seconds=60,
                warning_ttl_seconds=300,
            )

            first = await repository.record_message(
                chat_id=-100123,
                user_id=42,
                message_id=1,
                content_key="text:hello   world",
            )
            second = await repository.record_message(
                chat_id=-100123,
                user_id=42,
                message_id=2,
                content_key="text:HELLO world",
            )

            assert first.message_ids == (1,)
            assert second.message_ids == (1, 2)

            assert await repository.mark_warned_once(
                chat_id=-100123,
                user_id=42,
                digest=second.digest,
            )
            assert not await repository.mark_warned_once(
                chat_id=-100123,
                user_id=42,
                digest="another-digest",
            )

            warning_ttl = await redis.ttl(repository.warning_key(-100123, 42))
            state_ttl = await redis.ttl(repository.key(-100123, 42))
            assert 0 < warning_ttl <= 300
            assert 0 < state_ttl <= 60
            assert (
                await repository.get_warning_digest(
                    chat_id=-100123,
                    user_id=42,
                )
                == second.digest
            )
        finally:
            await redis.aclose()

    asyncio.run(run())


def test_redis_repositories_persist_runtime_settings_and_llm_cache(
    redis_endpoint: tuple[str, int],
) -> None:
    async def run() -> None:
        redis = redis_client(redis_endpoint)
        try:
            await redis.flushdb()
            settings_repository = RuntimeSettingsRepository(redis)
            cache_repository = LLMResultCacheRepository(redis, ttl_seconds=300)

            await settings_repository.set_action_mode(
                ActionMode.DELETE,
                chat_id=-100123,
            )
            await settings_repository.set_notification_target(
                chat_id=-100123,
                target="@admin",
            )
            await cache_repository.set("casino promo", "yes")

            assert (
                await settings_repository.get_action_mode(
                    default=ActionMode.NOTIFY_ADMIN,
                    chat_id=-100123,
                )
                == ActionMode.DELETE
            )
            assert (
                await settings_repository.get_notification_target(chat_id=-100123)
                == "@admin"
            )
            assert await cache_repository.get("CASINO   promo") == "yes"

            cache_ttl = await cache_repository.get_ttl("casino promo")
            assert cache_ttl is not None
            assert 0 < cache_ttl <= 300
        finally:
            await redis.aclose()

    asyncio.run(run())
