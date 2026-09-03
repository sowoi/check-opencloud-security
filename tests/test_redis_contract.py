"""
The two Redis backends have to answer the same questions the same way.

`webapp/redis_backend.py` ships two implementations of one protocol: the
`redis.asyncio` client every deployment runs, and the in-process `MemoryRedis`
selected by ``memory://`` that every other test in this suite runs. Until this
file existed, only the second one was ever executed. That is the classic shape
of a test double drifting away from the thing it stands in for: `MemoryRedis`
was the implementation under test, `_RealRedis` was the implementation in
production, and nothing checked that they agreed.

The commands here are the ones whose semantics are easy to get subtly wrong
and impossible to notice - `SET NX` returning whether it stored, `TTL`
answering -2 for a key that is gone and -1 for one that never expires, `LPOS`
counting from zero, `LREM` returning how many it removed, `INCR` leaving an
existing expiry alone. A divergence in any of them passes the whole suite and
then loses a scan, or serves one that should have expired, on a real server.

Every test is parametrised over both backends. The real one runs when
``TEST_REDIS_URL`` names a server - CI starts one, and `docker compose`
already provides one locally - and skips when it does not, so a contributor
without a Redis still gets the in-process half. It is deliberately not a
``COS_``-prefixed name: `conftest.clean_env` strips every one of those before
a test runs, which is exactly what it is for.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest

pytest.importorskip("redis", reason="the web application extra is not installed")

from webapp.redis_backend import (
    BackendHealth,
    MemoryRedis,
    RedisBackend,
    create_backend,
)
from webapp.settings import WebSettings


def settings(**overrides: Any) -> WebSettings:
    """Web settings carrying only what the queue reads off them."""
    defaults: dict[str, Any] = {"public_base_url": "http://testserver"}
    defaults.update(overrides)
    return WebSettings(**defaults)


ISOLATED_QUEUE = f"contract:{uuid.uuid4()}"


class _IsolatedQueueSettings(WebSettings):
    """
    Settings whose queue is this run's own rather than the deployment's.

    `WebSettings.queue_name` is a read-only constant on purpose: the API and
    the worker have to agree on one queue without being configured to, so it
    is not a field and cannot be passed in. A test that enqueued onto that
    name would hand its job to whatever worker is watching the server, and
    count whatever else is already waiting there, so the queue test points the
    same code at a name nothing else uses.
    """

    @property
    def queue_name(self) -> str:
        return ISOLATED_QUEUE


REAL_URL = os.environ.get("TEST_REDIS_URL", "")


_LOOP: asyncio.AbstractEventLoop | None = None


def _loop() -> asyncio.AbstractEventLoop:
    """
    The one event loop every call in this module runs on.

    `asyncio.run` would open and close a fresh loop per call, which the
    in-process backend does not notice and the real client cannot survive: a
    `redis.asyncio` pool binds its sockets to the loop that opened them, so the
    second call finds its connection attached to a loop that is already closed.
    Production runs one loop for the life of the process, and so does this.
    """
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    return _LOOP


def _run(coroutine):
    """Drive one coroutine to completion, the way the sync tests here read."""
    return _loop().run_until_complete(coroutine)


@pytest.fixture(scope="module", autouse=True)
def _close_the_loop_after_the_module():
    """Give the loop back at the end, rather than leaving it open for the run."""
    yield
    global _LOOP
    if _LOOP is not None and not _LOOP.is_closed():
        _LOOP.close()
    _LOOP = None


class _Namespaced:
    """
    A backend whose keys are all prefixed, so a shared server stays isolated.

    The real backend may be a Redis somebody else is also using - a developer's
    own container, or a CI service reused across jobs. Prefixing every key
    means a run cleans up exactly what it made and cannot see, or delete,
    anything else.
    """

    def __init__(self, inner: RedisBackend, prefix: str) -> None:
        self._inner = inner
        self._prefix = prefix
        self._touched: set[str] = set()

    def key(self, name: str) -> str:
        full = f"{self._prefix}{name}"
        self._touched.add(full)
        return full

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def cleanup(self) -> None:
        if self._touched:
            await self._inner.delete(*sorted(self._touched))


@pytest.fixture(params=["memory", "real"])
def store(request):
    """One backend, empty, under a prefix nothing else in this run uses."""
    prefix = f"contract:{uuid.uuid4()}:"
    if request.param == "memory":
        inner: RedisBackend = MemoryRedis()
    else:
        if not REAL_URL:
            pytest.skip("TEST_REDIS_URL is not set, so there is no real Redis to compare against")
        inner = create_backend(REAL_URL)
        try:
            _run(inner.ping())
        except Exception as exc:  # noqa: BLE001 - any failure to reach it is a skip
            _run(inner.close())
            pytest.skip(f"TEST_REDIS_URL is set but unreachable: {exc}")

    namespaced = _Namespaced(inner, prefix)
    try:
        yield namespaced
    finally:
        _run(namespaced.cleanup())
        _run(inner.close())


def test_a_key_that_was_never_written_reads_as_missing(store):
    """The distinction the whole store rests on: absent is None, not empty."""
    assert _run(store.get(store.key("absent"))) is None
    assert _run(store.ttl(store.key("absent"))) == -2
    assert _run(store.expire(store.key("absent"), 60)) is False
    assert _run(store.delete(store.key("absent"))) == 0


def test_a_value_reads_back_exactly_as_it_was_written(store):
    """Including the round trip through bytes the real client does and the fake does not."""
    key = store.key("value")

    assert _run(store.set(key, "a string with ünicode and \"quotes\"")) is True
    assert _run(store.get(key)) == 'a string with ünicode and "quotes"'
    assert _run(store.delete(key)) == 1
    assert _run(store.get(key)) is None


def test_setting_a_key_that_exists_is_refused_only_when_nx_is_asked_for(store):
    """`SET NX` is how a uuid is claimed; a wrong answer hands one scan two workers."""
    key = store.key("claim")

    assert _run(store.set(key, "first", nx=True)) is True
    assert _run(store.set(key, "second", nx=True)) is False
    assert _run(store.get(key)) == "first"
    assert _run(store.set(key, "third")) is True
    assert _run(store.get(key)) == "third"


def test_a_key_written_without_an_expiry_never_expires(store):
    """-1 and -2 are different answers and mean different things."""
    key = store.key("forever")
    _run(store.set(key, "value"))

    assert _run(store.ttl(key)) == -1
    assert _run(store.expire(key, 60)) is True
    assert 0 < _run(store.ttl(key)) <= 60


def test_writing_a_key_again_without_an_expiry_clears_the_one_it_had(store):
    """A rewrite that silently kept an old TTL would expire a fresh record early."""
    key = store.key("rewritten")
    _run(store.set(key, "value", ex=60))
    assert 0 < _run(store.ttl(key)) <= 60

    _run(store.set(key, "value again"))

    assert _run(store.ttl(key)) == -1


def test_incrementing_counts_from_nothing_and_keeps_the_expiry_it_was_given(store):
    """The rate limiter increments first and expires once; a reset window stops limiting."""
    key = store.key("counter")

    assert _run(store.incr(key)) == 1
    assert _run(store.expire(key, 60)) is True
    assert _run(store.incr(key)) == 2
    assert _run(store.get(key)) == "2"
    assert 0 < _run(store.ttl(key)) <= 60, "INCR must not clear the window's expiry"


def test_a_queue_keeps_its_order_and_reports_positions_from_zero(store):
    """`lpos` is the visitor's place in the queue; off by one is a wrong answer on a page."""
    key = store.key("queue")
    for value in ("first", "second", "third"):
        _run(store.rpush(key, value))

    assert _run(store.llen(key)) == 3
    assert _run(store.lpos(key, "first")) == 0
    assert _run(store.lpos(key, "third")) == 2
    assert _run(store.lpos(key, "never queued")) is None


def test_removing_one_entry_removes_the_first_and_says_how_many_it_removed(store):
    """A worker picking a job up removes exactly its own, not every copy of it."""
    key = store.key("queue")
    for value in ("a", "b", "a"):
        _run(store.rpush(key, value))

    assert _run(store.lrem(key, 1, "a")) == 1
    assert _run(store.llen(key)) == 2
    assert _run(store.lpos(key, "a")) == 1, "the second 'a' must be what is left"
    assert _run(store.lrem(key, 1, "not queued")) == 0


def test_an_empty_or_missing_list_answers_without_failing(store):
    """The queue is read on every status request, including before anything is in it."""
    key = store.key("empty")

    assert _run(store.llen(key)) == 0
    assert _run(store.lpos(key, "anything")) is None
    assert _run(store.lrem(key, 1, "anything")) == 0


def test_deleting_a_list_counts_it_once(store):
    """Erasure reports how much it erased; counting a key twice overstates it."""
    key = store.key("queue")
    _run(store.rpush(key, "only"))

    assert _run(store.delete(key)) == 1
    assert _run(store.llen(key)) == 0


def test_matching_keys_finds_the_prefix_and_nothing_either_side_of_it(store):
    """The one command that walks the keyspace, and the one that erases a target."""
    wanted = [store.key("scan:aaa:status"), store.key("scan:aaa:result")]
    other = store.key("scan:bbb:status")
    for key in [*wanted, other]:
        _run(store.set(key, "value"))

    found = _run(store.keys_matching(store.key("scan:aaa:*")))

    assert found == sorted(wanted)
    assert other not in found
    assert _run(store.keys_matching(store.key("scan:zzz:*"))) == []


def test_an_expiry_that_has_passed_takes_the_key_with_it(store):
    """
    Retention is a TTL and nothing else, so a key past its TTL must be gone.

    One second is a real wait against a real server, which is why the rest of
    the suite moves `MemoryRedis`'s clock instead. It is worth it exactly once:
    a TTL the fake honours and the server does not would keep every scan
    result for ever.
    """
    key = store.key("expiring")
    _run(store.set(key, "value", ex=1))
    assert _run(store.get(key)) == "value"

    if isinstance(store._inner, MemoryRedis):
        store._inner.advance(1.5)
    else:
        _run(asyncio.sleep(1.5))

    assert _run(store.get(key)) is None
    assert _run(store.ttl(key)) == -2


def test_health_reports_the_queue_depth_and_whether_a_worker_is_alive(store):
    """The public health probe is assembled from these two readings."""
    queue = store.key("queue")
    worker = store.key("worker")
    _run(store.rpush(queue, "job"))
    _run(store.set(worker, "alive", ex=60))

    health = _run(store.health(queue, worker))

    assert isinstance(health, BackendHealth)
    assert health.queue_depth == 1
    assert health.worker_alive is True


def test_health_says_no_worker_when_the_heartbeat_has_gone(store):
    """The negative half: a missing heartbeat is what 'no worker' actually looks like."""
    queue = store.key("queue")
    worker = store.key("worker")

    health = _run(store.health(queue, worker))

    assert health.queue_depth == 0
    assert health.worker_alive is False


def test_a_backend_answers_a_ping(store):
    """`create_backend` returning something unusable would fail far from here."""
    assert _run(store.ping()) is True


def test_every_call_in_this_file_runs_on_the_same_event_loop():
    """
    A fresh loop per call is what broke the real backend, and it broke quietly.

    `MemoryRedis` awaits nothing that belongs to a loop, so a per-call
    `asyncio.run` kept the memory half of every test above passing while the
    real client failed on the second command it was given. Asserting the loop
    itself is the only way that difference stays visible without a server.
    """

    async def running_loop() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    first = _run(running_loop())
    second = _run(running_loop())

    assert first is second
    assert not first.is_closed()


def test_a_memory_url_selects_the_queue_that_runs_nothing():
    """
    ``memory://`` has to keep choosing `InertQueue`, or the overload tests lie.

    Those tests observe a scan that stays queued for ever. If this URL ever
    reached a real pool, they would be watching a worker instead of a queue.
    """
    from webapp import queue

    chosen = _run(queue.create_queue(settings(redis_url="memory://tests")))

    assert isinstance(chosen, queue.InertQueue)
    _run(chosen.enqueue("some-uuid"))
    assert chosen.jobs == ["some-uuid"]
    _run(chosen.close())


def test_a_redis_url_is_turned_into_connection_settings_arq_understands():
    """
    The translation from this project's one URL setting to ARQ's own object.

    It is pure, so it is worth asserting without a server: a deployment whose
    host, port or database were dropped here would connect somewhere else
    entirely and simply never run a scan.
    """
    from webapp import queue

    parsed = queue.redis_settings(settings(redis_url="redis://user:secret@example.test:6380/3"))

    assert parsed.host == "example.test"
    assert parsed.port == 6380
    assert parsed.database == 3
    assert parsed.password == "secret"


@pytest.mark.skipif(not REAL_URL, reason="TEST_REDIS_URL is not set")
def test_a_real_url_selects_the_arq_queue_and_a_job_reaches_it():
    """
    The queue every deployment actually runs, which nothing else here touches.

    `InertQueue` is what the whole web suite enqueues onto, so the code that
    hands a job to a worker had never been executed. The job payload is the
    uuid and nothing else - no target and no waiver list travels through the
    queue - and this is the only place that claim is checked against a server.
    """
    from arq import create_pool

    from webapp import queue

    configured = _IsolatedQueueSettings(
        public_base_url="http://testserver", redis_url=REAL_URL
    )
    opened = _run(queue.create_queue(configured))
    reader = _run(create_pool(queue.redis_settings(configured)))
    backend = create_backend(REAL_URL)
    waiting: list[Any] = []
    try:
        assert isinstance(opened, queue.ArqQueue)
        _run(opened.enqueue("11111111-1111-4111-8111-111111111111"))

        # ARQ's queue is a sorted set of job ids, and the definition lives
        # beside it, so the queue is read back with ARQ's own reader rather
        # than the list commands the store's own queue answers to.
        waiting = _run(reader.queued_jobs(queue_name=ISOLATED_QUEUE))

        assert [job.function for job in waiting] == [queue.JOB_NAME]
        assert waiting[0].args == ("11111111-1111-4111-8111-111111111111",)
        assert waiting[0].kwargs == {}, "nothing but the uuid travels through the queue"
    finally:
        _run(opened.close())
        _run(reader.aclose())
        _run(backend.delete(ISOLATED_QUEUE, *(f"arq:job:{job.job_id}" for job in waiting)))
        _run(backend.close())
