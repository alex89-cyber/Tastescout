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

Formato de la respuesta final (Markdown, en el idioma del usuario):
## Quién es tu público
## Qué vender o agregar (3 ideas concretas)
## Con quién colaborar (marcas, artistas o lugares)
## Cómo hablarle (tono y temas para redes)
## Datos de Qloo usados
Cita las entidades de Qloo por nombre con su afinidad cuando la tengas.
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


def run_agent(llm: OpenAI, model: str, qloo: QlooClient, user_request: str, on_step=None) -> str:
    """Corre el ciclo herramienta→LLM. on_step(name, args, result) sirve para mostrar el avance."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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
