# scripts/test_scopus.py
# Versión que fuerza lectura de configuración

import os
import sys
from dotenv import load_dotenv

# Cargar .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

scopus_key = os.getenv("SCOPUS_API_KEY")

if not scopus_key:
    print("❌ ERROR: No se encontró SCOPUS_API_KEY en .env")
    sys.exit(1)

print("✅ SCOPUS_API_KEY encontrada en .env")
print("🔄 Intentando importar pybliometrics...")

try:
    from pybliometrics.scopus import ScopusSearch, init
    print("✅ pybliometrics importado correctamente")
except ImportError as e:
    print(f"❌ Error al importar: {e}")
    sys.exit(1)

# FORZAR inicialización
print("🔧 Verificando configuración...")
try:
    # Intentar inicializar si no existe config
    init()
except:
    pass  # Si ya existe, ignorar

print("\n🔄 Probando búsqueda en Scopus...")
print("Query: 'artificial intelligence' AND 'employment' (últimos 2 años)\n")

try:
    query = 'TITLE-ABS-KEY("artificial intelligence" AND "employment") AND PUBYEAR > 2022'

    search = ScopusSearch(query, refresh=True)

    total = search.get_results_size()
    print(f"✅ ¡ÉXITO! Conexión a Scopus funcionando")
    print(f"📊 Papers encontrados: {total}")

    results = search.results
    if results:
        print("\n📄 Primeros 3 papers:")
        for i, paper in enumerate(results[:3], 1):
            print(f"\n{i}. {paper.title}")
            print(f"   Autores: {paper.author_names}")
            print(f"   Año: {paper.coverDate[:4] if paper.coverDate else 'N/A'}")
            print(f"   DOI: {paper.doi if paper.doi else 'N/A'}")

    print("\n" + "="*60)
    print("✅ CHECKPOINT 2 COMPLETADO: Scopus funcionando")

except Exception as e:
    error_msg = str(e)
    print(f"\n❌ ERROR: {error_msg}")

    if "401" in error_msg or "Unauthorized" in error_msg:
        print("\n💡 API Key inválida o sin permisos institucionales")
    elif "429" in error_msg:
        print("\n💡 Límite de requests alcanzado. Espera 5 minutos.")
    elif "configuration" in error_msg.lower():
        print("\n💡 Problema de configuración. Probemos método alternativo...")
        print("Ejecuta: python scripts/test_scopus_simple.py")
    else:
        print("\n💡 Verifica acceso a internet")
