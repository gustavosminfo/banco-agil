"""
ui/api_client.py
Cliente HTTP para o AgentOS — usado pela UI Streamlit.
"""

import json
import os
from typing import Iterator

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
            # Um único turno pode encadear várias chamadas internas ao modelo
            # (coordenador decide → delega → membro raciocina/chama ferramenta →
            # coordenador processa tags → resposta final). Já observamos casos
            # reais em produção levando ~6,5min (13 chamadas sequenciais à
            # DeepInfra) para uma única requisição. 600s dá margem confortável
            # sem desistir antes do AgentOS responder.
            timeout=600.0,
        )

    def run(self, team_id: str, message: str, session_id: str, user_id: str | None = None) -> dict:
        """Executa um turno de conversa contra /teams/{team_id}/runs.

        O endpoint do AgentOS espera multipart/form-data (não JSON) — usar
        `data=` em vez de `json=` aqui.

        `user_id` (CPF, depois de autenticado) escopa a memória do cliente —
        sem ele, todas as conversas compartilhariam o mesmo "usuário"
        anônimo, misturando memórias entre clientes diferentes.
        """
        data = {"message": message, "session_id": session_id, "stream": "false"}
        if user_id:
            data["user_id"] = user_id
        response = self.client.post(f"/teams/{team_id}/runs", data=data)
        response.raise_for_status()
        return response.json()

    def run_stream(
        self, team_id: str, message: str, session_id: str, user_id: str | None = None
    ) -> Iterator[str]:
        """Executa um turno via SSE, gerando os pedaços de texto (`TeamRunContent`)
        conforme chegam.

        Usar streaming aqui não é só estético: como cada `yield` devolve o
        controle ao loop do Streamlit, um clique em outro widget (ex.: "Nova
        sessão") consegue interromper a execução em andamento — com a chamada
        síncrona antiga (`run`, `stream=false`), a UI ficava travada por até
        os 600s de timeout sem processar nenhum evento.
        """
        data = {"message": message, "session_id": session_id, "stream": "true"}
        if user_id:
            data["user_id"] = user_id
        with self.client.stream("POST", f"/teams/{team_id}/runs", data=data) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[len("data: "):])
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "TeamRunContent" and isinstance(event.get("content"), str):
                    yield event["content"]
