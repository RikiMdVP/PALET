# scripts/test_scopus.py
# Versión simplificada sin configuración compleja

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

scopus_key = os.getenv("SCOPUS_API_KEY")

if not scopus_key:
    print("❌ ERROR: No se encontró SCOPUS_API_KEY en .env")
    print("\n📋 PASOS PARA OBTENER TU API KEY:")
    print("1. Contacta a biblioteca@uniovi.es")
    print("2. O registra en: https://dev.elsevier.com/")
    print("3. Añade la key a tu archivo .env")
    sys.exit(1)

print("✅ SCOPUS_API_KEY encontrada en .env")
print("🔄 Intentando importar pybliometrics...")

try:
    from pybliometrics.scopus import ScopusSearch
    print("✅ pybliometrics importado correctamente")
except ImportError as e:
    print(f"❌ Error al importar: {e}")
    print("\n💡 Solución:")
    print("pip uninstall pybliometrics -y")
    print("pip install pybliometrics")
    sys.exit(1)

print("\n🔄 Probando búsqueda en Scopus...")
print("Query: 'artificial intelligence' AND 'employment' (últimos 2 años)")

try:
    query = 'TITLE-ABS-KEY("artificial intelligence" AND "employment") AND PUBYEAR > 2022'

    search = ScopusSearch(query, refresh=True)

    total = search.get_results_size()
    print(f"\n✅ ¡ÉXITO! Conexión a Scopus funcionando")
    print(f"📊 Papers encontrados: {total}")

    # Obtener primeros resultados
    results = search.results
    if results:
        print("\n📄 Primeros 3 papers:")
        for i, paper in enumerate(results[:3], 1):
            print(f"\n{i}. {paper.title}")
            print(f"   Autores: {paper.author_names}")
            print(f"   Año: {paper.coverDate[:4] if paper.coverDate else 'N/A'}")
            print(f"   DOI: {paper.doi if paper.doi else 'N/A'}")

    print("\n" + "="*60)
    print("✅ CHECKPOINT 2 COMPLETADO: Scopus funcionando correctamente")

except Exception as e:
    error_msg = str(e)
    print(f"\n❌ ERROR: {error_msg}")

    if "401" in error_msg or "Unauthorized" in error_msg:
        print("\n💡 API Key inválida o sin permisos institucionales")
    elif "429" in error_msg:
        print("\n💡 Límite de requests alcanzado. Espera unos minutos.")
    else:
        print("\n💡 Verifica tu conexión a internet y permisos institucionales")
