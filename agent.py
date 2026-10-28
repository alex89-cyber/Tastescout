"""Agente TasteScout: un LLM que decide qué consultar en Qloo y luego recomienda.

Usa la API compatible con OpenAI, así que funciona con OpenAI, Gemini, Groq,
Claude (endpoint compatible) u otro proveedor, cambiando LLM_BASE_URL y LLM_MODEL.
"""

from __future__ import annotations

import json

from openai import OpenAI

from qloo_client import ENTITY_TYPES, QlooClient, QlooError

MAX_STEPS = 8

SYSTEM_PROMPT = """Eres TasteScout, un estratega de negocio para pequeños comercios.
Tu trabajo: con datos de gustos de Qloo, decirle al usuario qué vender, con quién
colaborar y cómo comunicarse con el público de su zona.

Cómo trabajas:
1. Si el usuario menciona gustos, marcas, artistas o lugares de referencia,
   búscalos con search_entities para obtener sus IDs.
2. Llama a get_insights para 3 o 4 tipos distintos (por ejemplo place, brand,
   artist) usando la ubicación y los IDs encontrados como señales.
3. Responde SOLO con base en lo que regresó Qloo. No inventes entidades ni
   rasgos del público (ocupación, edad, transporte, hábitos) que Qloo no dio.
   Describe al público a partir de las entidades con más afinidad y nómbralas.
   Si sugieres algo que es tu interpretación y no un dato, márcalo como
   "(sugerencia)".
4. Los lugares traen "in_zone": si es false, el lugar está cerca pero fuera
   de la zona; prioriza los que tienen true y, si mencionas uno con false,
   di que está en una colonia vecina.

Formato de la respuesta final (Markdown, en el idioma del usuario):
## Quién es tu público
## Qué vender o agregar (3 ideas concretas)
## Con quién colaborar (marcas, artistas o lugares)
## Cómo hablarle (tono y temas para redes)
Cita las entidades de Qloo por nombre con su afinidad cuando la tengas.
No repitas al final la lista completa de datos: la app ya la muestra en tarjetas.
"""

COMPARE_PROMPT = """Eres TasteScout, un estratega de negocio para pequeños comercios.
El usuario quiere decidir entre DOS zonas para su negocio. Tu trabajo: comparar
los gustos del público de cada zona con datos de Qloo y recomendar una.

Cómo trabajas:
1. Si el usuario menciona gustos de referencia, búscalos con search_entities.
2. Para CADA zona, llama a get_insights con los MISMOS tipos (place, brand,
   artist y uno más si aporta), usando la zona como location y los mismos IDs
   de referencia. Así la comparación es justa.
3. Responde SOLO con base en lo que regresó Qloo. No inventes entidades ni
   rasgos del público. Marca tus interpretaciones como "(sugerencia)".
4. Los lugares traen "in_zone": si es false, el lugar está cerca pero fuera
   de la zona; prioriza los que tienen true y, si mencionas uno con false,
   di que está en una colonia vecina.
5. Artistas y podcasts suelen variar poco entre zonas; busca las diferencias
   sobre todo en lugares y marcas.

Formato de la respuesta final (Markdown, en el idioma del usuario):
## Veredicto
Una línea: qué zona recomiendas para este negocio y por qué.
## En qué se parecen
## En qué se diferencian
Compara afinidades: qué entidades destacan solo en una zona.
## Cómo adaptar el negocio a cada zona
Una lista corta por zona (menú, colaboraciones, tono).
Cita las entidades de Qloo por nombre con su afinidad cuando la tengas.
No repitas al final la lista completa de datos: la app ya la muestra en tarjetas.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": "Busca una entidad en Qloo por nombre y regresa su ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nombre a buscar"},
                    "entity_type": {"type": "string", "enum": list(ENTITY_TYPES)},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_insights",
            "description": (
                "Recomendaciones de Qloo de un tipo de entidad, con afinidad, "
                "sesgadas por la ubicación y por IDs de gustos de referencia."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string", "enum": list(ENTITY_TYPES)},
                    "location": {"type": "string", "description": "Ciudad o colonia"},
                    "seed_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs de search_entities (opcional)",
                    },
                    "take": {"type": "integer", "minimum": 3, "maximum": 15},
                },
                "required": ["entity_type"],
            },
        },
    },
]


def _run_tool(qloo: QlooClient, name: str, args: dict):
    try:
        if name == "search_entities":
            return qloo.search(args["query"], args.get("entity_type"))
        if name == "get_insights":
            return qloo.insights(
                args["entity_type"],
                location=args.get("location"),
                seed_ids=args.get("seed_ids"),
                take=args.get("take", 8),
            )
        return {"error": f"Herramienta desconocida: {name}"}
    except QlooError as e:
        return {"error": str(e)}


def run_agent(
    llm: OpenAI,
    model: str,
    qloo: QlooClient,
    user_request: str,
    on_step=None,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    """Corre el ciclo herramienta→LLM. on_step(name, args, result) sirve para mostrar el avance."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]
    for _ in range(MAX_STEPS):
        reply = llm.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        msg = reply.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = _run_tool(qloo, call.function.name, args)
            if on_step:
                on_step(call.function.name, args, result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    # Si se acabaron los pasos, pide la respuesta final sin herramientas.
    messages.append({"role": "user", "content": "Ya no consultes más. Da tu respuesta final."})
    reply = llm.chat.completions.create(model=model, messages=messages)
    return reply.choices[0].message.content or ""


CALENDAR_PROMPT = """Con base en el plan de abajo, arma un calendario de publicaciones
en redes sociales de 4 semanas, 3 publicaciones por semana (12 en total).
Usa solo las entidades de Qloo y las ideas que aparecen en el plan.

Responde SOLO con un arreglo JSON, sin texto extra ni bloques de código, así:
[{"semana": 1, "dia": "Lunes", "formato": "Reel", "tema": "...", "inspiracion": "entidad de Qloo o idea del plan"}]

Plan:
"""


def make_calendar(llm: OpenAI, model: str, plan: str) -> list[dict]:
    """Calendario de 4 semanas a partir del plan. Lista vacía si el LLM no da JSON válido."""
    reply = llm.chat.completions.create(
        model=model, messages=[{"role": "user", "content": CALENDAR_PROMPT + plan}]
    )
    text = reply.choices[0].message.content or ""
    start, end = text.find("["), text.rfind("]")
    try:
        rows = json.loads(text[start : end + 1])
    except ValueError:
        return []
    keys = ("semana", "dia", "formato", "tema", "inspiracion")
    return [{k: row.get(k, "") for k in keys} for row in rows if isinstance(row, dict)]
