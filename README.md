# TasteScout 🧭

Agente de IA para pequeños negocios: le das tu giro y tu zona, consulta los gustos
de la gente en Qloo Taste AI™ y te dice qué vender, con quién colaborar y cómo
comunicarte. Hecho con Python, Streamlit y un LLM con llamadas a herramientas.

## Cómo funciona

1. El usuario escribe negocio, ubicación, gustos de referencia y objetivo.
2. El LLM decide qué consultar y llama a dos herramientas:
   - `search_entities` → `GET /search` (convierte "Bad Bunny" en un ID de Qloo)
   - `get_insights` → `GET /v2/insights` (lugares, marcas, artistas… con afinidad,
     usando la ubicación y los IDs como señales)
3. Con los resultados, el LLM escribe un plan: público, qué vender, colaboraciones,
   tono en redes y los datos de Qloo que usó.
4. La app muestra cada paso del agente y las llamadas exactas a la API.

## Probar en tu compu (Windows)

```powershell
cd tastescout
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
notepad .streamlit\secrets.toml      # pega tu key de Qloo y la del LLM
streamlit run app.py
```

Sin `QLOO_API_KEY`, la app entra en modo de prueba con datos falsos
(`mock_data.json`), para revisar la interfaz.

## Desplegar en Streamlit Community Cloud

1. Sube esta carpeta a un repo público de GitHub. **No subas `secrets.toml`**
   (ya está en `.gitignore`).
2. Entra a https://share.streamlit.io → **Create app** → elige el repo y `app.py`.
3. En **Advanced settings → Secrets**, pega el contenido de tu `secrets.toml`.
4. Deploy. Esa URL pública es la que va en Devpost.
