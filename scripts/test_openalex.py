# scripts/test_openalex.py
# Alternativa gratuita a Scopus

from pyalex import Works
import pandas as pd
import os

print("🔄 Probando OpenAlex (alternativa gratuita a Scopus)...")
print("Query: 'artificial intelligence' AND 'employment'\n")

# Búsqueda
works = Works().search("artificial intelligence employment").get()

print(f"✅ OpenAlex funcionando")
print(f"📊 Papers encontrados: {len(works)}\n")

print("📄 Primeros 3 papers:\n")

for i, work in enumerate(works[:3], 1):
    title = work.get('title', 'Sin título')
    authors = ', '.join([a['author']['display_name'] for a in work.get('authorships', [])][:3])
    year = work.get('publication_year', 'N/A')
    doi = work.get('doi', 'N/A')

    print(f"{i}. {title}")
    print(f"   Autores: {authors}")
    print(f"   Año: {year}")
    print(f"   DOI: {doi}\n")

# Guardar CSV
data = []
for work in works[:50]:
    data.append({
        'title': work.get('title'),
        'authors': ', '.join([a['author']['display_name'] for a in work.get('authorships', [])]),
        'year': work.get('publication_year'),
        'doi': work.get('doi'),
        'abstract': work.get('abstract_inverted_index')
    })

df = pd.DataFrame(data)
output_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'data', 'raw', 'test_openalex_output.csv'
)
df.to_csv(output_path, index=False, encoding='utf-8')

print("="*60)
print("✅ OpenAlex funcionando correctamente")
print(f"💾 Guardado en: data/raw/test_openalex_output.csv")
print("="*60)
