"""TasteScout: qué vender y a quién, según los gustos de tu zona (Qloo + LLM)."""

import os

import streamlit as st
from openai import APIStatusError, OpenAI

from agent import run_agent
from qloo_client import client_from_env


def secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:  # no hay secrets.toml en local
        return os.environ.get(name, default)


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

with st.form("brief"):
    col1, col2 = st.columns(2)
    business = col1.text_input("Tu negocio", "Cafetería de especialidad")
    location = col2.text_input("Ciudad o colonia", "Roma Norte, Ciudad de México")
    references = st.text_input(
        "Gustos de referencia de tu cliente ideal (opcional, separados por coma)",
        "Bad Bunny, Blue Bottle Coffee",
    )
    goal = st.selectbox(
        "¿Qué quieres decidir?",
        ["Qué agregar a mi menú o catálogo", "Con qué marcas o artistas colaborar", "Cómo comunicarme en redes", "Todo lo anterior"],
        index=3,
    )
    submitted = st.form_submit_button("Analizar mi zona", type="primary")

if submitted:
    request = (
        f"Negocio: {business}\nUbicación: {location}\n"
        f"Gustos de referencia: {references or 'ninguno'}\nObjetivo: {goal}"
    )
    llm = OpenAI(api_key=llm_key, base_url=llm_base_url or None, max_retries=4)
    steps = st.status("El agente está consultando Qloo…", expanded=True)

    def show_step(name, args, result):
        n = len(result) if isinstance(result, list) else 0
        steps.write(f"**{name}** `{args}` → {n} resultados")

    try:
        try:
            answer = run_agent(llm, llm_model, qloo, request, on_step=show_step)
        except APIStatusError as e:
            if not llm_fallback or e.status_code not in (429, 500, 503):
                raise
            steps.write(f"`{llm_model}` está saturado ({e.status_code}); reintentando con `{llm_fallback}`…")
            qloo.log.clear()
            answer = run_agent(llm, llm_fallback, qloo, request, on_step=show_step)
        steps.update(label=f"Listo: {len(qloo.log)} consultas a Qloo", state="complete", expanded=False)
        st.markdown(answer)
    except Exception as e:
        steps.update(label="Algo falló", state="error")
        st.error(f"Error: {e}")
        if not qloo.log:
            st.info(f"El error vino del LLM, no de Qloo. Si es 503, el modelo está saturado: espera un minuto y reintenta. Modelo: `{llm_model}` · URL: `{llm_base_url or 'OpenAI'}`")

    with st.expander("Ver las llamadas a la API de Qloo"):
        st.json(qloo.log)
