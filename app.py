"""TasteScout: qué vender y a quién, según los gustos de tu zona (Qloo + LLM)."""

import os

import streamlit as st
from openai import APIStatusError, OpenAI

from agent import COMPARE_PROMPT, SYSTEM_PROMPT, run_agent
from qloo_client import client_from_env

TYPE_LABELS = {
    "place": "📍 Lugares",
    "brand": "🛍️ Marcas",
    "artist": "🎵 Artistas",
    "podcast": "🎙️ Podcasts",
    "movie": "🎬 Películas",
    "tv_show": "📺 Series",
    "book": "📚 Libros",
    "destination": "✈️ Destinos",
}


def secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:  # no hay secrets.toml en local
        return os.environ.get(name, default)


def entity_card(entity):
    """Una tarjeta con nombre, detalle y barra de afinidad."""
    with st.container(border=True):
        st.markdown(f"**{entity['name']}**")
        detail = entity.get("address") or ", ".join(entity.get("tags") or [])
        if detail:
            st.caption(detail)
        affinity = entity.get("affinity")
        if isinstance(affinity, (int, float)):
            st.progress(min(max(float(affinity), 0.0), 1.0), text=f"Afinidad {affinity:.0%}")


def group_insights(collected):
    """{(tipo, zona): resultados}, quedándose con la última consulta de cada par."""
    groups = {}
    for item in collected:
        groups[(item["type"], item["location"])] = item["results"]
    return groups


def render_single(collected):
    st.subheader("Lo que Qloo encontró en tu zona")
    for (etype, _), results in group_insights(collected).items():
        if not results:
            continue
        st.markdown(f"#### {TYPE_LABELS.get(etype, etype)}")
        cols = st.columns(4)
        for i, entity in enumerate(results[:4]):
            with cols[i]:
                entity_card(entity)


def render_compare(collected):
    groups = group_insights(collected)
    zones = list(dict.fromkeys(loc for _, loc in groups if loc))[:2]
    if len(zones) < 2:
        render_single(collected)
        return
    st.subheader("Lo que Qloo encontró en cada zona")

    # Entidades que aparecen en ambas zonas: el público que comparten.
    names = [{e["name"] for (_, loc), res in groups.items() if loc == z for e in res} for z in zones]
    shared = sorted(names[0] & names[1])
    if shared:
        st.markdown("**En común en ambas zonas:** " + " · ".join(f"`{n}`" for n in shared[:12]))

    types = list(dict.fromkeys(t for t, _ in groups))
    for etype in types:
        st.markdown(f"#### {TYPE_LABELS.get(etype, etype)}")
        cols = st.columns(2)
        for col, zone in zip(cols, zones):
            with col:
                st.caption(zone)
                for entity in groups.get((etype, zone), [])[:4]:
                    entity_card(entity)


st.set_page_config(page_title="TasteScout", page_icon="🧭", layout="wide")
st.title("🧭 TasteScout")
st.caption("Qué vender, con quién colaborar y cómo hablarle a tu público, según los gustos reales de tu zona. Con datos de Qloo Taste AI™.")

qloo = client_from_env(secret)
llm_key = secret("LLM_API_KEY")
llm_model = secret("LLM_MODEL", "gpt-4o-mini")
# Modelo de respaldo si el principal está saturado (503) o sin cuota (429).
llm_fallback = secret("LLM_FALLBACK_MODEL")
llm_base_url = secret("LLM_BASE_URL")  # vacío = OpenAI

if qloo.mock:
    st.warning("Modo de prueba: sin QLOO_API_KEY, la app usa datos de ejemplo, no datos de Qloo.")
if not llm_key:
    st.error("Falta LLM_API_KEY en los secrets. Revisa el README.")
    st.stop()

mode = st.radio("¿Qué quieres hacer?", ["Analizar mi zona", "Comparar dos zonas"], horizontal=True)
compare = mode == "Comparar dos zonas"

with st.form("brief"):
    business = st.text_input("Tu negocio", "Cafetería de especialidad")
    if compare:
        col1, col2 = st.columns(2)
        zone_a = col1.text_input("Zona A", "Roma Norte, Ciudad de México")
        zone_b = col2.text_input("Zona B", "Coyoacán, Ciudad de México")
    else:
        location = st.text_input("Ciudad o colonia", "Roma Norte, Ciudad de México")
    references = st.text_input(
        "Gustos de referencia de tu cliente ideal (opcional, separados por coma)",
        "Bad Bunny, Blue Bottle Coffee",
    )
    if not compare:
        goal = st.selectbox(
            "¿Qué quieres decidir?",
            ["Qué agregar a mi menú o catálogo", "Con qué marcas o artistas colaborar", "Cómo comunicarme en redes", "Todo lo anterior"],
            index=3,
        )
    submitted = st.form_submit_button("Comparar zonas" if compare else "Analizar mi zona", type="primary")

if submitted:
    if compare:
        request = (
            f"Negocio: {business}\nZona A: {zone_a}\nZona B: {zone_b}\n"
            f"Gustos de referencia: {references or 'ninguno'}\n"
            "Objetivo: decidir en cuál de las dos zonas abrir o enfocarme."
        )
        prompt = COMPARE_PROMPT
    else:
        request = (
            f"Negocio: {business}\nUbicación: {location}\n"
            f"Gustos de referencia: {references or 'ninguno'}\nObjetivo: {goal}"
        )
        prompt = SYSTEM_PROMPT

    llm = OpenAI(api_key=llm_key, base_url=llm_base_url or None, max_retries=4)
    steps = st.status("El agente está consultando Qloo…", expanded=True)
    collected = []

    def show_step(name, args, result):
        n = len(result) if isinstance(result, list) else 0
        steps.write(f"**{name}** `{args}` → {n} resultados")
        if name == "get_insights" and isinstance(result, list):
            collected.append({"type": args.get("entity_type"), "location": args.get("location") or "", "results": result})

    def run(model):
        return run_agent(llm, model, qloo, request, on_step=show_step, system_prompt=prompt)

    try:
        try:
            answer = run(llm_model)
        except APIStatusError as e:
            if not llm_fallback or e.status_code not in (429, 500, 503):
                raise
            steps.write(f"`{llm_model}` está saturado ({e.status_code}); reintentando con `{llm_fallback}`…")
            qloo.log.clear()
            collected.clear()
            answer = run(llm_fallback)
        steps.update(label=f"Listo: {len(qloo.log)} consultas a Qloo", state="complete", expanded=False)
        st.markdown(answer)
        st.divider()
        if compare:
            render_compare(collected)
        else:
            render_single(collected)
    except Exception as e:
        steps.update(label="Algo falló", state="error")
        st.error(f"Error: {e}")
        if not qloo.log:
            st.info(f"El error vino del LLM, no de Qloo. Si es 503, el modelo está saturado: espera un minuto y reintenta. Modelo: `{llm_model}` · URL: `{llm_base_url or 'OpenAI'}`")

    with st.expander("Ver las llamadas a la API de Qloo"):
        st.json(qloo.log)
