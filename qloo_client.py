"""Cliente mínimo para la API de Qloo (key del hackatón).

La key solo vive en el servidor (secrets de Streamlit o variable de entorno).
Nunca se manda al navegador ni se guarda en el repo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

DEFAULT_BASE_URL = "https://hackathon.api.qloo.com"

# Tipos de entidad útiles para un negocio local.
ENTITY_TYPES = {
    "place": "urn:entity:place",
    "brand": "urn:entity:brand",
    "artist": "urn:entity:artist",
    "movie": "urn:entity:movie",
    "tv_show": "urn:entity:tv_show",
    "podcast": "urn:entity:podcast",
    "book": "urn:entity:book",
    "destination": "urn:entity:destination",
}


class QlooError(RuntimeError):
    pass


def _simplify(entity: dict) -> dict:
    """Se queda solo con lo que el agente necesita, para no gastar tokens."""
    props = entity.get("properties") or {}
    query = entity.get("query") or {}
    tags = [t.get("name") for t in (entity.get("tags") or [])[:5] if t.get("name")]
    return {
        "id": entity.get("entity_id") or entity.get("id"),
        "name": entity.get("name"),
        "type": entity.get("type") or (entity.get("types") or [None])[0],
        "affinity": query.get("affinity"),
        "popularity": entity.get("popularity"),
        "tags": tags,
        "address": props.get("address"),
    }


def _results(payload: dict) -> list[dict]:
    results = payload.get("results", [])
    if isinstance(results, dict):
        results = results.get("entities", [])
    return results or []


class QlooClient:
    def __init__(self, api_key: str | None, base_url: str = DEFAULT_BASE_URL, mock: bool = False):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.mock = mock or not api_key
        # Registro de cada llamada, para mostrarlo en la app.
        self.log: list[dict] = []

    def _get(self, path: str, params: dict) -> dict:
        params = {k: v for k, v in params.items() if v not in (None, "", [])}
        if self.mock:
            payload = _mock_response(path, params)
            self.log.append({"path": path, "params": params, "status": "mock"})
            return payload
        resp = requests.get(
            f"{self.base_url}{path}",
            params=params,
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
            timeout=20,
        )
        self.log.append({"path": path, "params": params, "status": resp.status_code})
        if resp.status_code == 404:
            return {"results": []}
        if resp.status_code in (401, 403):
            raise QlooError("Qloo rechazó la key (401/403). Revisa QLOO_API_KEY y la URL base.")
        if resp.status_code == 429:
            raise QlooError("Llegaste al límite de llamadas de Qloo (429). Espera un momento.")
        if not resp.ok:
            raise QlooError(f"Qloo respondió {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def search(self, query: str, entity_type: str | None = None, take: int = 5) -> list[dict]:
        params = {"query": query, "take": take}
        if entity_type:
            params["types"] = ENTITY_TYPES.get(entity_type, entity_type)
        return [_simplify(e) for e in _results(self._get("/search", params))]

    def insights(
        self,
        entity_type: str,
        location: str | None = None,
        seed_ids: list[str] | None = None,
        take: int = 10,
    ) -> list[dict]:
        """Recomendaciones de un tipo de entidad, sesgadas por gustos (seeds) y/o ubicación."""
        params = {
            "filter.type": ENTITY_TYPES.get(entity_type, entity_type),
            "signal.interests.entities": ",".join(seed_ids or []),
            "take": take,
        }
        if location:
            # Para lugares, filtra a la ciudad; para lo demás, usa la ciudad como señal de gusto.
            key = "filter.location.query" if entity_type == "place" else "signal.location.query"
            params[key] = location
        return [_simplify(e) for e in _results(self._get("/v2/insights", params))]


def client_from_env(get_secret=None) -> QlooClient:
    """Lee la configuración de st.secrets (si se pasa) o de variables de entorno."""
    def read(name, default=None):
        if get_secret:
            value = get_secret(name)
            if value:
                return value
        return os.environ.get(name, default)

    return QlooClient(
        api_key=read("QLOO_API_KEY"),
        base_url=read("QLOO_BASE_URL", DEFAULT_BASE_URL),
        mock=str(read("QLOO_MOCK", "")).lower() in ("1", "true", "yes"),
    )


# --- Datos de ejemplo para probar la app sin key -----------------------------

_MOCK = json.loads((Path(__file__).parent / "mock_data.json").read_text(encoding="utf-8"))


def _mock_response(path: str, params: dict) -> dict:
    if path == "/search":
        q = params.get("query", "").lower()
        hits = [e for e in _MOCK["entities"] if q in e["name"].lower()] or _MOCK["entities"][:2]
        return {"results": hits[: int(params.get("take", 5))]}
    wanted = params.get("filter.type")
    hits = [e for e in _MOCK["entities"] if e["types"][0] == wanted]
    return {"results": {"entities": hits[: int(params.get("take", 10))]}}
