# scripts/arq_module.py
# Módulo ARQ: Automated Research Query
# Extrae Research Questions y keywords desde un seed prompt

import os
import sys
import json
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Inicializar cliente Claude
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("ERROR: No se encontró ANTHROPIC_API_KEY en .env")
    sys.exit(1)

client = Anthropic(api_key=api_key)

# Cargar prompt del sistema
prompt_system_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'prompts',
    'arq_system_v3.txt'
)

try:
    with open(prompt_system_path, 'r', encoding='utf-8') as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    print(f"ERROR: No se encontró {prompt_system_path}")
    print("Asegúrate de haber creado el archivo prompts/arq_system_v3.txt")
    sys.exit(1)


def extract_keywords(seed_prompt: str, verbose: bool = True) -> dict:
    """
    Extrae Research Questions y keywords desde un seed prompt.

    Args:
        seed_prompt: Texto descriptivo del usuario sobre su revisión
        verbose: Si True, muestra información de progreso

    Returns:
        dict con 'research_questions', 'keywords', 'reasoning', 'timestamp'
    """

    if verbose:
        print("Procesando seed prompt con Claude...")
        print(f"Longitud del prompt: {len(seed_prompt)} caracteres\n")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Seed prompt:\n\n{seed_prompt}"
                }
            ]
        )

        # Extraer respuesta
        response_text = response.content[0].text.strip()

        # Limpiar posibles markdown code blocks
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "").strip()

        # Parsear JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            print("ERROR: Claude no devolvió JSON válido")
            print(f"Respuesta recibida (primeros 500 chars):\n{response_text[:500]}")
            print(f"\nError de parsing: {e}")
            raise

        # Añadir metadata
        result['timestamp'] = datetime.now().isoformat()
        result['tokens_used'] = {
            'input': response.usage.input_tokens,
            'output': response.usage.output_tokens,
            'total': response.usage.input_tokens + response.usage.output_tokens
        }

        # Calcular coste aproximado
        cost_input = response.usage.input_tokens * 0.000003  # $3 per million
        cost_output = response.usage.output_tokens * 0.000015  # $15 per million
        result['cost_usd'] = round(cost_input + cost_output, 6)

        if verbose:
            print("Extracción completada\n")
            print("=" * 60)
            print("RESEARCH QUESTIONS:")
            for i, rq in enumerate(result['research_questions'], 1):
                print(f"  {i}. {rq}")

            print(f"\nKEYWORDS ({len(result['keywords'])}):")
            for kw in result['keywords']:
                print(f"  - {kw}")

            print(f"\nREASONING:")
            print(f"  {result['reasoning']}")

            print(f"\nTOKENS: {result['tokens_used']['input']} in, {result['tokens_used']['output']} out")
            print(f"COST: ${result['cost_usd']}")
            print("=" * 60)

        return result

    except Exception as e:
        print(f"ERROR inesperado: {e}")
        raise


def save_arq_output(result: dict, filename: str = None) -> str:
    """
    Guarda el resultado de ARQ en un archivo JSON.

    Args:
        result: Diccionario con el output de extract_keywords
        filename: Nombre del archivo (opcional, se genera automático si None)

    Returns:
        Path del archivo guardado
    """

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"arq_output_{timestamp}.json"

    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'outputs',
        'json'
    )

    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, filename)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nResultado guardado en: {output_path}")

    return output_path


def interactive_refinement(initial_result: dict, original_prompt: str) -> dict:
    """
    Permite al usuario refinar keywords interactivamente.

    Args:
        initial_result: Output inicial de extract_keywords
        original_prompt: Seed prompt original

    Returns:
        Resultado refinado
    """

    print("\n" + "=" * 60)
    print("REFINAMIENTO INTERACTIVO")
    print("=" * 60)
    print("\nOpciones:")
    print("  1. Aceptar resultado")
    print("  2. Añadir keywords manualmente")
    print("  3. Eliminar keywords")
    print("  4. Regenerar con feedback adicional")
    print("  5. Cancelar")

    choice = input("\nSelecciona opción (1-5): ").strip()

    if choice == "1":
        print("Resultado aceptado")
        return initial_result

    elif choice == "2":
        new_kw = input("\nAñade keywords separadas por coma: ").strip()
        if new_kw:
            new_keywords = [kw.strip() for kw in new_kw.split(",") if kw.strip()]
            initial_result['keywords'].extend(new_keywords)
            initial_result['reasoning'] += f"\n[Usuario añadió: {', '.join(new_keywords)}]"
            print(f"Añadidas {len(new_keywords)} keywords")
        return initial_result

    elif choice == "3":
        print("\nKeywords actuales:")
        for i, kw in enumerate(initial_result['keywords'], 1):
            print(f"  {i}. {kw}")

        to_remove = input("\nNúmeros a eliminar (separados por coma, ej: 1,3,5): ").strip()
        if to_remove:
            try:
                indices = [int(i.strip()) - 1 for i in to_remove.split(",") if i.strip().isdigit()]
                removed = [initial_result['keywords'][i] for i in indices if i < len(initial_result['keywords'])]
                initial_result['keywords'] = [
                    kw for i, kw in enumerate(initial_result['keywords'])
                    if i not in indices
                ]
                initial_result['reasoning'] += f"\n[Usuario eliminó: {', '.join(removed)}]"
                print(f"Eliminadas {len(removed)} keywords")
            except (ValueError, IndexError) as e:
                print(f"Error en selección: {e}")
        return initial_result

    elif choice == "4":
        print("\n" + "=" * 60)
        feedback = input("Feedback para Claude (ej: 'más enfoque en Europa', 'incluir políticas'): ").strip()

        if not feedback:
            print("No se proporcionó feedback, manteniendo resultado original")
            return initial_result

        # Crear nuevo prompt con contexto
        refined_prompt = f"""
Prompt original del usuario:
{original_prompt}

Primera iteración generó:
- Research Questions: {initial_result['research_questions']}
- Keywords: {initial_result['keywords']}

Feedback del usuario para refinamiento:
{feedback}

Por favor, genera una versión mejorada considerando este feedback.
"""

        print("\nRegenerando con feedback...")
        return extract_keywords(refined_prompt, verbose=True)

    else:
        print("Cancelado")
        return initial_result


def validate_arq_output(result: dict) -> tuple[bool, list]:
    """
    Valida que el output tenga el formato correcto.

    Args:
        result: Diccionario a validar

    Returns:
        (bool, list): (es_valido, lista_de_errores)
    """

    errors = []

    # Verificar keys requeridas
    required_keys = ['research_questions', 'keywords', 'reasoning']
    for key in required_keys:
        if key not in result:
            errors.append(f"Falta key requerida: '{key}'")

    # Opcionales pero recomendados
    for key in ['inclusion_criteria', 'exclusion_criteria']:
        if key not in result:
            result[key] = []

    if errors:
        return False, errors

    # Verificar tipos
    if not isinstance(result['research_questions'], list):
        errors.append("'research_questions' debe ser una lista")

    if not isinstance(result['keywords'], list):
        errors.append("'keywords' debe ser una lista")

    if not isinstance(result['reasoning'], str):
        errors.append("'reasoning' debe ser un string")

    # Verificar rangos razonables
    if isinstance(result['research_questions'], list):
        if not (1 <= len(result['research_questions']) <= 5):
            errors.append(f"Se esperan 1-5 Research Questions, se encontraron {len(result['research_questions'])}")

    if isinstance(result['keywords'], list):
        if not (5 <= len(result['keywords']) <= 20):
            errors.append(f"Se esperan 5-20 keywords, se encontraron {len(result['keywords'])}")

    return len(errors) == 0, errors


# Script principal si se ejecuta directamente
if __name__ == "__main__":
    print("=" * 60)
    print("  MÓDULO ARQ - Automated Research Query")
    print("=" * 60)

    # Opciones de ejecución
    print("\nModo de ejecución:")
    print("  1. Usar ejemplo predefinido")
    print("  2. Introducir seed prompt manualmente")
    print("  3. Leer desde archivo")

    mode = input("\nSelecciona modo (1-3): ").strip()

    if mode == "1":
        # Ejemplo predefinido
        seed_prompt = """
        Quiero hacer una revisión sistemática sobre el impacto de la
        inteligencia artificial en el mercado laboral europeo, con
        especial énfasis en los sectores que están experimentando mayor
        automatización. Me interesa entender tanto la destrucción como
        la creación de empleo, y las políticas que se están implementando
        para gestionar esta transición.
        """

    elif mode == "2":
        # Input manual
        print("\nIntroduce tu seed prompt (termina con línea vacía):")
        lines = []
        while True:
            line = input()
            if line.strip() == "":
                break
            lines.append(line)
        seed_prompt = "\n".join(lines)

        if not seed_prompt.strip():
            print("ERROR: Seed prompt vacío")
            sys.exit(1)

    elif mode == "3":
        # Leer desde archivo
        filepath = input("\nRuta del archivo: ").strip()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                seed_prompt = f.read()
        except FileNotFoundError:
            print(f"ERROR: No se encontró el archivo {filepath}")
            sys.exit(1)
    else:
        print("Opción inválida")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("SEED PROMPT:")
    print("=" * 60)
    print(seed_prompt.strip())
    print("=" * 60 + "\n")

    # Extraer keywords
    result = extract_keywords(seed_prompt, verbose=True)

    # Validar output
    is_valid, errors = validate_arq_output(result)
    if not is_valid:
        print("\nADVERTENCIA: Output no pasó validación:")
        for error in errors:
            print(f"  - {error}")

    # Guardar resultado
    output_file = save_arq_output(result)

    # Opción de refinamiento
    refine = input("\n¿Refinar resultado? (s/n): ").strip().lower()
    if refine == 's':
        result = interactive_refinement(result, seed_prompt)
        save_arq_output(result, filename="arq_output_refined.json")

    print("\nProceso ARQ completado")
