def test_guardar_y_obtener(tmp_skills):
    tmp_skills.guardar("test rutina", ["echo a", "echo b"], "descripcion test")
    s = tmp_skills.obtener("Test Rutina")
    assert s is not None
    assert len(s["comandos"]) == 2


def test_persistencia(tmp_skills, tmp_path):
    tmp_skills.guardar("morning", ["code", "spotify"])

    from backend.modulos.skills import Skills
    s2 = Skills(path=tmp_skills._path)
    assert s2.obtener("morning") is not None


def test_eliminar(tmp_skills):
    tmp_skills.guardar("foo", ["bar"])
    assert tmp_skills.eliminar("foo")
    assert tmp_skills.obtener("foo") is None
    assert not tmp_skills.eliminar("foo")


def test_listar(tmp_skills):
    tmp_skills.guardar("uno", ["a"])
    tmp_skills.guardar("dos", ["b", "c"])
    lista = tmp_skills.listar()
    assert len(lista) == 2
    nombres = {s["nombre"] for s in lista}
    assert nombres == {"uno", "dos"}


def test_normalizacion_nombre(tmp_skills):
    tmp_skills.guardar("  CamelCase  ", ["x"])
    assert tmp_skills.obtener("camelcase") is not None
    assert tmp_skills.obtener("CAMELCASE") is not None
