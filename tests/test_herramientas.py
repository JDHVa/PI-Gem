import pytest
import asyncio
from backend.modulos import herramientas as tools


@pytest.mark.asyncio
async def test_escribir_y_leer(tmp_workdir):
    r1 = await tools.escribir_archivo("test.txt", "hola mundo")
    assert r1["exito"]
    r2 = await tools.leer_archivo("test.txt")
    assert r2["exito"]
    assert r2["resultado"] == "hola mundo"


@pytest.mark.asyncio
async def test_editar_archivo(tmp_workdir):
    await tools.escribir_archivo("e.txt", "foo bar baz")
    r = await tools.editar_archivo("e.txt", "bar", "QUUX")
    assert r["exito"]
    r2 = await tools.leer_archivo("e.txt")
    assert "QUUX" in r2["resultado"]


@pytest.mark.asyncio
async def test_editar_archivo_no_existe(tmp_workdir):
    r = await tools.editar_archivo("nope.txt", "x", "y")
    assert not r["exito"]


@pytest.mark.asyncio
async def test_editar_archivo_patron_no_encontrado(tmp_workdir):
    await tools.escribir_archivo("a.txt", "contenido")
    r = await tools.editar_archivo("a.txt", "XYZ_no_existe", "nada")
    assert not r["exito"]


@pytest.mark.asyncio
async def test_listar_directorio(tmp_workdir):
    await tools.escribir_archivo("a.txt", "1")
    await tools.escribir_archivo("b.txt", "2")
    r = await tools.listar_directorio(".")
    assert r["exito"]
    assert "a.txt" in r["resultado"]
    assert "b.txt" in r["resultado"]


@pytest.mark.asyncio
async def test_buscar_en_archivos(tmp_workdir):
    await tools.escribir_archivo("uno.py", "def foo():\n    pass")
    await tools.escribir_archivo("dos.py", "def bar():\n    pass")
    r = await tools.buscar_en_archivos("foo", ".", ".py")
    assert r["exito"]
    assert "uno.py" in r["resultado"]


@pytest.mark.asyncio
async def test_mover_archivo(tmp_workdir):
    await tools.escribir_archivo("origen.txt", "x")
    r = await tools.mover_archivo("origen.txt", "destino.txt")
    assert r["exito"]
    r2 = await tools.leer_archivo("destino.txt")
    assert r2["exito"]


@pytest.mark.asyncio
async def test_eliminar_sin_confirmacion_falla(tmp_workdir):
    """Crítico: el LLM no puede auto-confirmar."""
    tools.set_confirmacion_callback(None)
    await tools.escribir_archivo("borrar.txt", "x")
    r = await tools.eliminar("borrar.txt")
    assert not r["exito"]
    r2 = await tools.leer_archivo("borrar.txt")
    assert r2["exito"]


@pytest.mark.asyncio
async def test_eliminar_con_confirmacion(tmp_workdir):
    async def autorizar(accion, args):
        return True
    tools.set_confirmacion_callback(autorizar)
    try:
        await tools.escribir_archivo("a_borrar.txt", "x")
        r = await tools.eliminar("a_borrar.txt")
        assert r["exito"]
    finally:
        tools.set_confirmacion_callback(None)


@pytest.mark.asyncio
async def test_eliminar_con_rechazo(tmp_workdir):
    async def rechazar(accion, args):
        return False
    tools.set_confirmacion_callback(rechazar)
    try:
        await tools.escribir_archivo("no_borrar.txt", "x")
        r = await tools.eliminar("no_borrar.txt")
        assert not r["exito"]
    finally:
        tools.set_confirmacion_callback(None)


@pytest.mark.asyncio
async def test_ejecutar_herramienta_desconocida(tmp_workdir):
    r = await tools.ejecutar("herramienta_que_no_existe", {})
    assert not r["exito"]
    assert "desconocida" in r["error"].lower()


@pytest.mark.asyncio
async def test_args_invalidos(tmp_workdir):
    r = await tools.ejecutar("escribir_archivo", {"foo": "bar"})
    assert not r["exito"]
