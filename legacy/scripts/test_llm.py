# scripts/test_llm.py
# Propósito: Verificar conexión con Claude

import os
import sys
from anthropic import Anthropic
from dotenv import load_dotenv

# Añadir la raíz del proyecto al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Cargar .env desde la raíz del proyecto
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Inicializar cliente
api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    print("❌ ERROR: No se encontró ANTHROPIC_API_KEY en .env")
    print(f"Buscando en: {os.path.dirname(os.path.dirname(__file__))}/.env")
    sys.exit(1)

client = Anthropic(api_key=api_key)

print("🔄 Enviando mensaje a Claude...")

try:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": "Di 'Hola' y confirma que PALET está listo para configurarse."
            }
        ]
    )
    
    print("\n✅ ¡ÉXITO! Claude respondió:")
    print("-" * 50)
    print(response.content[0].text)
    print("-" * 50)
    print(f"\n📊 Tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out")
    print(f"💰 Costo: ${(response.usage.input_tokens * 0.000003 + response.usage.output_tokens * 0.000015):.6f}")
    
except Exception as e:
    print(f"❌ ERROR: {e}")