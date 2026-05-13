"""
Motor agéntico de GEM con function calling.

Reemplaza el flujo viejo [CMD:...] por function calling nativo.
Gemini decide qué herramientas usar y cuándo parar.
"""

import asyncio
import logging
from typing import Callable

from google.genai import types
from backend.config import ajustes
from backend.modulos import herramientas as tools
from backend.modulos.gemini_cliente import _get_cliente

log = logging.getLogger("gem.agente")

SYSTEM_AGENTE = """\
Eres GEM, asistente de IA personal. Tienes acceso a herramientas para
interactuar con la computadora del usuario directamente.

REGLAS:
- Cuando el usuario pide hacer algo en su PC (crear archivos, instalar,
  organizar carpetas, correr comandos), usa las herramientas. NO le
  expliques cómo hacerlo: hazlo tú.
- Trabaja sistemáticamente: analiza, ejecuta paso a paso, verifica.
- Si un paso falla, intenta corregirlo (máx 2 reintentos por herramienta).
- Al terminar, resume brevemente qué hiciste (1-2 frases).
- Para conversación normal (preguntas, charla), responde directo sin herramientas.
- Personalidad: directo, técnico, español de México, sin formalismos.
- Workdir por defecto: {workdir}

CONTEXTO:
{contexto}
"""

ICONOS = {
    "bash":               "⚡",
    "leer_archivo":       "📖",
    "escribir_archivo":   "✏️",
    "editar_archivo":     "🔧",
    "listar_directorio":  "📂",
    "crear_directorio":   "📁",
    "buscar_en_archivos": "🔍",
    "mover_archivo":      "📦",
    "eliminar":           "🗑️",
}


class AgenteGEM:
    def __init__(self):
        self._abortando = False

    def abortar(self) -> None:
        self._abortando = True

    async def ejecutar(
        self,
        tarea: str,
        historial_gem: list[dict],
        contexto_rag: str = "",
        on_paso: Callable | None = None,
    ) -> str:
        self._abortando = False
        cliente = _get_cliente()

        if on_paso:
            await on_paso({"tipo": "inicio", "tarea": tarea})

        contents: list[types.Content] = []
        for turno in historial_gem[-10:]:
            rol = "user" if turno["rol"] == "user" else "model"
            contents.append(types.Content(
                role=rol,
                parts=[types.Part.from_text(text=turno["texto"])]
            ))

        if contents and contents[-1].role == "user":
            contents[-1] = types.Content(
                role="user",
                parts=[types.Part.from_text(text=tarea)]
            )
        else:
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=tarea)]
            ))

        system_prompt = SYSTEM_AGENTE.format(
            workdir=str(tools.WORKDIR),
            contexto=contexto_rag or "Sin contexto previo.",
        )

        cfg = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tools.DECLARACIONES],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
            temperature=0.3,
            max_output_tokens=2048,
        )

        pasos = 0

        for _ in range(ajustes.agente_max_pasos):
            if self._abortando:
                return "Tarea cancelada."

            if on_paso:
                await on_paso({"tipo": "pensando"})

            def _llamar():
                return cliente.models.generate_content(
                    model=ajustes.gemini_modelo,
                    contents=contents,
                    config=cfg,
                )

            try:
                respuesta = await asyncio.to_thread(_llamar)
            except Exception as e:
                log.error("Gemini error en agente: %s", e)
                return f"Error al comunicarme con Gemini: {e}"

            candidato = respuesta.candidates[0]
            partes = candidato.content.parts or []

            llamadas = [p for p in partes if getattr(p, "function_call", None)]
            textos   = [p.text for p in partes if getattr(p, "text", None) and p.text.strip()]

            if not llamadas:
                texto_final = " ".join(textos) if textos else "Listo."
                if on_paso:
                    await on_paso({"tipo": "fin", "texto": texto_final, "pasos": pasos})
                return texto_final

            contents.append(candidato.content)

            partes_resultado: list[types.Part] = []
            for parte in partes:
                if not getattr(parte, "function_call", None):
                    continue
                fc      = parte.function_call
                nombre  = fc.name
                args    = dict(fc.args) if fc.args else {}
                icono   = ICONOS.get(nombre, "🔩")
                pasos  += 1

                log.info("Agente paso %d: %s(%s)", pasos, nombre, list(args.keys()))

                if on_paso:
                    await on_paso({
                        "tipo": "herramienta_llama",
                        "nombre": nombre, "args": args,
                        "icono": icono, "paso": pasos,
                    })

                resultado = await tools.ejecutar(nombre, args)

                if resultado.get("exito"):
                    res_str = str(resultado.get("resultado", "OK"))[:2000]
                    if on_paso:
                        await on_paso({
                            "tipo": "herramienta_ok", "nombre": nombre,
                            "resultado": res_str, "paso": pasos,
                        })
                else:
                    res_str = f"ERROR: {resultado.get('error', 'desconocido')}"
                    if on_paso:
                        await on_paso({
                            "tipo": "herramienta_error", "nombre": nombre,
                            "error": resultado.get("error", ""), "paso": pasos,
                        })

                partes_resultado.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=nombre,
                            response={"output": res_str},
                        )
                    )
                )

            contents.append(types.Content(role="user", parts=partes_resultado))

        return f"Alcancé el límite de {ajustes.agente_max_pasos} pasos."
