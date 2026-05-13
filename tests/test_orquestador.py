def test_construir_prompt_basico():
    from backend.prompts.system_prompt import construir
    p = construir(
        emocion="alegre",
        es_usuario=True,
        turnos=3,
        memoria={"conversaciones": 5},
        silenciado=False,
        fragmentos_rag=["fragmento uno", "fragmento dos"],
        perfil_visual="perfil de prueba",
    )
    assert "alegre" in p
    assert "perfil de prueba" in p
    assert "fragmento uno" in p


def test_construir_prompt_sin_fragmentos():
    from backend.prompts.system_prompt import construir
    p = construir(fragmentos_rag=[])
    assert "Sin contexto previo" in p


def test_construir_prompt_silenciado():
    from backend.prompts.system_prompt import construir
    p = construir(silenciado=True)
    assert "Sí" in p or "sí" in p


def test_regex_agente_detecta():
    from backend.orquestador import _REGEX_AGENTE
    assert _REGEX_AGENTE.search("crea una carpeta nueva")
    assert _REGEX_AGENTE.search("instala numpy")
    assert _REGEX_AGENTE.search("ejecuta este comando")
    assert _REGEX_AGENTE.search("haz un archivo de configuración")


def test_regex_agente_no_detecta_charla():
    from backend.orquestador import _REGEX_AGENTE
    assert not _REGEX_AGENTE.search("cuál es la capital de Francia")
    assert not _REGEX_AGENTE.search("hola, cómo estás")
    assert not _REGEX_AGENTE.search("cuéntame un chiste")


def test_regex_skill_guardar():
    from backend.orquestador import _REGEX_GUARDAR_SKILL
    m = _REGEX_GUARDAR_SKILL.match("guarda rutina mañana: abre code; abre spotify")
    assert m
    assert m.group(1).strip() == "mañana"
    assert "code" in m.group(2)


def test_regex_skill_ejecutar():
    from backend.orquestador import _REGEX_EJECUTAR_SKILL
    m = _REGEX_EJECUTAR_SKILL.match("ejecuta rutina mañana")
    assert m
    assert m.group(1).strip() == "mañana"


def test_regex_screenshot():
    from backend.orquestador import _REGEX_SCREENSHOT
    assert _REGEX_SCREENSHOT.search("mira mi pantalla")
    assert _REGEX_SCREENSHOT.search("qué ves en la pantalla")
    assert _REGEX_SCREENSHOT.search("analiza mi screen")
