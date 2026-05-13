def test_historial_vacio(historial_tmp):
    assert historial_tmp.cargar() == []


def test_guardar_y_cargar(historial_tmp):
    h = [
        {"rol": "user", "texto": "hola"},
        {"rol": "model", "texto": "qué tal"},
    ]
    historial_tmp.guardar(h)
    assert historial_tmp.cargar() == h


def test_truncado_max_turnos(historial_tmp):
    from backend.config import ajustes
    n = ajustes.historial_max_turnos * 2 + 10
    h = [{"rol": "user" if i % 2 == 0 else "model", "texto": f"msg{i}"}
         for i in range(n)]
    historial_tmp.guardar(h)
    cargado = historial_tmp.cargar()
    assert len(cargado) == ajustes.historial_max_turnos * 2


def test_limpiar(historial_tmp):
    historial_tmp.guardar([{"rol": "user", "texto": "x"}])
    historial_tmp.limpiar()
    assert historial_tmp.cargar() == []


def test_archivo_corrupto(historial_tmp, tmp_path):
    historial_tmp._path.write_text("no es json válido")
    assert historial_tmp.cargar() == []
