import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_cache_embeddings_evita_recomputo():
    from backend.modulos import gemini_cliente
    from backend.modulos.gemini_cliente import generar_embedding, set_cliente

    fake_emb_resp = MagicMock()
    fake_emb_resp.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]

    fake_cliente = MagicMock()
    fake_cliente.models.embed_content.return_value = fake_emb_resp

    set_cliente(fake_cliente)
    gemini_cliente._emb_cache._data.clear()

    try:
        r1 = await generar_embedding("hola mundo")
        r2 = await generar_embedding("hola mundo")
        assert r1 == r2
        assert fake_cliente.models.embed_content.call_count == 1
    finally:
        set_cliente(None)


@pytest.mark.asyncio
async def test_cache_queries_distintas():
    from backend.modulos import gemini_cliente
    from backend.modulos.gemini_cliente import generar_embedding, set_cliente

    fake_resp = MagicMock()
    fake_resp.embeddings = [MagicMock(values=[0.1])]
    fake_cliente = MagicMock()
    fake_cliente.models.embed_content.return_value = fake_resp

    set_cliente(fake_cliente)
    gemini_cliente._emb_cache._data.clear()

    try:
        await generar_embedding("query 1")
        await generar_embedding("query 2")
        assert fake_cliente.models.embed_content.call_count == 2
    finally:
        set_cliente(None)


def test_cache_lru_evict():
    from backend.modulos.gemini_cliente import _CacheLRU
    c = _CacheLRU(max_size=3)
    c.put("a", [1])
    c.put("b", [2])
    c.put("c", [3])
    c.put("d", [4])
    assert c.get("a") is None
    assert c.get("b") == [2]
    assert c.get("d") == [4]


def test_cache_lru_actualiza_orden():
    from backend.modulos.gemini_cliente import _CacheLRU
    c = _CacheLRU(max_size=2)
    c.put("a", [1])
    c.put("b", [2])
    c.get("a")
    c.put("c", [3])
    assert c.get("a") == [1]
    assert c.get("b") is None


@pytest.mark.asyncio
async def test_generar_respuesta_mock():
    from backend.modulos.gemini_cliente import generar_respuesta, set_cliente

    fake = MagicMock()
    fake_resp = MagicMock()
    fake_resp.text = "respuesta de prueba"
    fake.models.generate_content.return_value = fake_resp

    set_cliente(fake)
    try:
        r = await generar_respuesta(
            [{"rol": "user", "texto": "hola"}], system_prompt="test"
        )
        assert r == "respuesta de prueba"
    finally:
        set_cliente(None)
