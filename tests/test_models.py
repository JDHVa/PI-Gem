import sys
import os

# Añadir el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.modulos.gemini_cliente import _get_cliente
from google.genai import types
from google import genai

def probar_modelo(nombre_modelo: str):
    regiones_a_probar = ["global", "us-central1", "us-east5", "us-west1", "europe-west4"]
    print(f"\n--- Probando modelo: {nombre_modelo} ---")
    
    from backend.config import ajustes
    
    for region in regiones_a_probar:
        try:
            # Crear un cliente temporal para esta región
            cliente = genai.Client(
                vertexai=True,
                project=ajustes.vertex_project,
                location=region,
            )
            respuesta = cliente.models.generate_content(
                model=nombre_modelo,
                contents=["Di 'Hola' en una sola palabra."],
            )
            print(f"[OK] ÉXITO en la región {region}. Respuesta: {respuesta.text.strip()}")
            return # Terminamos si encontramos una región que funciona
        except Exception as e:
            if "404" in str(e) or "NOT_FOUND" in str(e) or "400" in str(e):
                continue # Probamos la siguiente
            else:
                print(f"[WARN] Error inesperado en {region}: {e}")
    
    print(f"[ERROR]: El modelo {nombre_modelo} no se encontró en ninguna de las regiones probadas.")

if __name__ == "__main__":
    print("Iniciando pruebas de Modelos de Gemini...")
    modelos_a_probar = [
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-preview",
        "gemini-3.1-pro-preview",
    ]
    
    for mod in modelos_a_probar:
        probar_modelo(mod)
