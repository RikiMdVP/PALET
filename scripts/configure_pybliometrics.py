# scripts/configure_pybliometrics.py
# Configurar pybliometrics una sola vez

import os
from dotenv import load_dotenv
from pybliometrics.scopus import init

# Cargar .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

api_key = os.getenv("SCOPUS_API_KEY")

if not api_key:
    print("❌ No se encontró SCOPUS_API_KEY en .env")
    exit(1)

print("🔧 Configurando pybliometrics...")
print(f"📝 API Key: {api_key[:10]}...{api_key[-4:]}")

try:
    # Usar init() en lugar de create_config()
    init()

    print("\n✅ Se iniciará configuración interactiva")
    print("📋 Cuando te pregunte por la API key, pégala y presiona Enter")
    print(f"\n🔑 Tu API key es: {api_key}")
    print("\nPara las demás opciones, solo presiona Enter (usa defaults)")

except Exception as e:
    print(f"❌ Error: {e}")
