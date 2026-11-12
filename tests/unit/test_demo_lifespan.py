from types import SimpleNamespace

import pytest

from apps.demo import app as demo_app


class ClosableClient:
    def __init__(self, *, fail_close=False):
        self.closed = False
        self.fail_close = fail_close

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("close failed")


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)

    def factory(*, injected_runner=False, injected_intent=False, fail_close=False):
        intent = ClosableClient(fail_close=fail_close)
        llm = ClosableClient(fail_close=fail_close)
        runner = SimpleNamespace(intent_client=intent, llm_client=llm)
        monkeypatch.setattr(demo_app, "PipelineRunner", lambda **kwargs: runner)
        app = demo_app.create_app(
            db_path=str(tmp_path / "demo.sqlite"),
            runner=runner if injected_runner else None,
            intent_client=intent if injected_intent else None,
        )
        return app, intent, llm

    return factory


async def test_injected_runner_clients_remain_open(make_app):
    app, intent, llm = make_app(injected_runner=True)
    async with app.router.lifespan_context(app):
        pass
    assert not intent.closed
    assert not llm.closed


async def test_injected_intent_remains_open_while_owned_llm_closes(make_app):
    app, intent, llm = make_app(injected_intent=True)
    async with app.router.lifespan_context(app):
        pass
    assert not intent.closed
    assert llm.closed


async def test_internally_created_clients_close(make_app):
    app, intent, llm = make_app()
    async with app.router.lifespan_context(app):
        pass
    assert intent.closed
    assert llm.closed


async def test_owned_clients_close_when_lifespan_body_raises(make_app):
    app, intent, llm = make_app()
    with pytest.raises(RuntimeError, match="application failed"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("application failed")
    assert intent.closed
    assert llm.closed


async def test_all_owned_clients_attempt_close_when_close_raises(make_app):
    app, intent, llm = make_app(fail_close=True)
    with pytest.raises(RuntimeError, match="close failed"):
        async with app.router.lifespan_context(app):
            pass
    assert intent.closed
    assert llm.closed
