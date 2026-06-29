"""
ui/api_client.py
Cliente HTTP para o AgentOS — usado pela UI Streamlit.
"""

import os

import httpx


class BancoAgilClient:
    """Cliente fino para o endpoint REST de runs do AgentOS."""

    def __init__(self) -> None:
        agentos_url = os.getenv("AGENTOS_URL", "http://localhost:8000")
        agentos_api_key = os.getenv("AGENTOS_API_KEY", "")

        headers = {}
        if agentos_api_key:
            headers["Authorization"] = f"Bearer {agentos_api_key}"

        self.client = httpx.Client(
            base_url=agentos_url,
            headers=headers,
            # Modelos "Thinking" (coordinator/Triagem/Entrevista) podem levar mais de
            # um minuto por turno — timeout curto demais derruba a conversa no meio.
            timeout=180.0,
        )

    def run(self, team_id: str, message: str, session_id: str) -> dict:
        """Executa um turno de conversa contra /teams/{team_id}/runs.

        O endpoint do AgentOS espera multipart/form-data (não JSON) — usar
        `data=` em vez de `json=` aqui.
        """
        response = self.client.post(
            f"/teams/{team_id}/runs",
            data={"message": message, "session_id": session_id, "stream": "false"},
        )
        response.raise_for_status()
        return response.json()
