"""
ui/streamlit_app.py
Interface Streamlit do Banco Ágil — consome o AgentOS via REST.

Execução:
    streamlit run ui/streamlit_app.py

Variáveis de ambiente necessárias (.env):
    AGENTOS_URL=http://localhost:8000
    AGENTOS_API_KEY=...
"""

import re
import uuid

import streamlit as st

from banco_agil.team import (
    limpar_tags_da_resposta,
    extrair_info_auth,
    detectar_encerramento,
)
from banco_agil.config import MAX_AUTH_ATTEMPTS
from ui.api_client import BancoAgilClient

TEAM_ID = "banco-agil"

# ── Configuração da página ────────────────────────────────────────────────────

st.set_page_config(
    page_title="Banco Ágil — Atendimento Virtual",
    page_icon="🏦",
    layout="centered",
)

# ── CSS customizado ────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .stChatMessage { border-radius: 12px; }
    .auth-badge {
        background: #ECFDF5; color: #065F46;
        border: 1px solid #A7F3D0;
        padding: 6px 12px; border-radius: 99px;
        font-size: 13px; display: inline-block; margin-bottom: 8px;
    }
    .blocked-badge {
        background: #FEF2F2; color: #991B1B;
        border: 1px solid #FECACA;
        padding: 6px 12px; border-radius: 99px;
        font-size: 13px; display: inline-block; margin-bottom: 8px;
    }
    .attempts-badge {
        background: #FFFBEB; color: #92400E;
        border: 1px solid #FDE68A;
        padding: 6px 12px; border-radius: 99px;
        font-size: 13px; display: inline-block; margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ── Inicialização do estado Streamlit ─────────────────────────────────────────

def _init_state() -> None:
    """Inicializa variáveis de sessão do Streamlit."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    if "client" not in st.session_state:
        st.session_state.client = BancoAgilClient()

    if "messages" not in st.session_state:
        st.session_state.messages = []          # [(role, content), ...]

    # Estado de autenticação — controlado localmente para feedback imediato na UI
    if "autenticado" not in st.session_state:
        st.session_state.autenticado     = False
    if "nome_cliente" not in st.session_state:
        st.session_state.nome_cliente    = None
    if "tentativas_auth" not in st.session_state:
        st.session_state.tentativas_auth = 0
    if "encerrado" not in st.session_state:
        st.session_state.encerrado       = False


def _resetar_sessao() -> None:
    """Reinicia completamente a sessão de atendimento."""
    for key in ["session_id", "client", "messages",
                "autenticado", "nome_cliente",
                "tentativas_auth", "encerrado"]:
        st.session_state.pop(key, None)
    st.rerun()


# ── Header ────────────────────────────────────────────────────────────────────

def _renderizar_header() -> None:
    col1, col2 = st.columns([5, 1])
    with col1:
        st.title("🏦 Banco Ágil")
        st.caption("Atendimento Virtual · Powered by Agno + AgentOS + DeepInfra")
    with col2:
        st.write("")
        if st.button("🔄 Nova sessão", use_container_width=True):
            _resetar_sessao()


def _renderizar_status() -> None:
    """Exibe badges de autenticação e tentativas."""
    if st.session_state.encerrado:
        st.markdown(
            '<span class="blocked-badge">🔒 Atendimento encerrado</span>',
            unsafe_allow_html=True,
        )
    elif st.session_state.autenticado:
        nome = st.session_state.nome_cliente or "Cliente"
        st.markdown(
            f'<span class="auth-badge">✅ Autenticado: {nome}</span>',
            unsafe_allow_html=True,
        )
    elif st.session_state.tentativas_auth > 0:
        restantes = MAX_AUTH_ATTEMPTS - st.session_state.tentativas_auth
        st.markdown(
            f'<span class="attempts-badge">'
            f'⚠️ Tentativas restantes: {restantes} de {MAX_AUTH_ATTEMPTS}'
            f'</span>',
            unsafe_allow_html=True,
        )


# ── Histórico de mensagens ────────────────────────────────────────────────────

def _renderizar_historico() -> None:
    for role, content in st.session_state.messages:
        avatar = "🏦" if role == "assistant" else "👤"
        with st.chat_message(role, avatar=avatar):
            st.markdown(content)


# ── Mensagem de boas-vindas ───────────────────────────────────────────────────

def _mensagem_boas_vindas() -> None:
    if not st.session_state.messages:
        bv = (
            "Olá! Bem-vindo(a) ao **Banco Ágil**. 😊\n\n"
            "Para iniciar o atendimento, precisarei verificar seus dados. "
            "Por favor, informe seu **CPF**."
        )
        st.session_state.messages.append(("assistant", bv))
        with st.chat_message("assistant", avatar="🏦"):
            st.markdown(bv)


# ── Processamento da mensagem ─────────────────────────────────────────────────

def _processar_mensagem(user_input: str) -> None:
    """Envia mensagem ao AgentOS via REST e processa a resposta."""

    # 1. Adicionar mensagem do usuário ao histórico
    st.session_state.messages.append(("user", user_input))
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    # 2. Bloquear se sessão encerrada
    if st.session_state.encerrado:
        msg_enc = "Esta sessão foi encerrada. Clique em **🔄 Nova sessão** para reiniciar."
        st.session_state.messages.append(("assistant", msg_enc))
        with st.chat_message("assistant", avatar="🏦"):
            st.markdown(msg_enc)
        return

    # 3. Chamar o AgentOS
    with st.chat_message("assistant", avatar="🏦"):
        with st.spinner("Analisando..."):
            try:
                run = st.session_state.client.run(
                    team_id=TEAM_ID,
                    message=user_input,
                    session_id=st.session_state.session_id,
                )
                resposta_raw: str = run.get("content", "")
            except Exception as exc:
                resposta_raw = (
                    "Desculpe, tivemos uma instabilidade temporária. "
                    f"Tente novamente em instantes. ({type(exc).__name__})"
                )

    # 4. Extrair metadados e limpar tags
    _processar_tags_resposta(resposta_raw)
    resposta_limpa = limpar_tags_da_resposta(resposta_raw)

    # 5. Exibir e salvar resposta
    with st.chat_message("assistant", avatar="🏦"):
        st.markdown(resposta_limpa)
    st.session_state.messages.append(("assistant", resposta_limpa))

    # 6. Verificar encerramento (tag real emitida pela ferramenta do agente)
    if detectar_encerramento(resposta_raw):
        st.session_state.encerrado = True


def _processar_tags_resposta(resposta: str) -> None:
    """Extrai tags ocultas da resposta e atualiza o estado do Streamlit."""

    # Autenticação bem-sucedida
    dados_auth = extrair_info_auth(resposta)
    if dados_auth and not st.session_state.autenticado:
        st.session_state.autenticado       = True
        st.session_state.nome_cliente      = dados_auth["nome"]
        st.session_state.cpf_cliente       = dados_auth["cpf"]   # type: ignore[attr-defined]
        st.session_state.tentativas_auth   = 0

    # Falha de autenticação
    if "[AUTH_FAIL]" in resposta.upper():
        st.session_state.tentativas_auth += 1
        if st.session_state.tentativas_auth >= MAX_AUTH_ATTEMPTS:
            st.session_state.encerrado = True

    # Score atualizado
    m_score = re.search(r"\[ROUTE\|credito\|score_atualizado=(\d+)\]", resposta, re.I)
    if m_score:
        st.session_state.score_atual = int(m_score.group(1))  # type: ignore[attr-defined]


# ── Sidebar com instruções de teste ──────────────────────────────────────────

def _renderizar_sidebar() -> None:
    with st.sidebar:
        st.header("📋 Guia de testes")
        st.markdown("""
**Clientes de teste:**

| CPF | Nascimento | Score | Limite |
|-----|-----------|-------|--------|
| 123.456.789-01 | 15/05/1990 | 720 | R$ 5.000 |
| 987.654.321-00 | 23/11/1985 | 450 | R$ 1.500 |
| 111.222.333-00 | 08/03/1978 | 610 | R$ 3.000 |
| 444.555.666-77 | 30/07/2000 | 380 | R$ 800 |
| 555.666.777-88 | 12/01/1995 | 810 | R$ 8.000 |

---
**Fluxos disponíveis:**
1. 🔐 Autenticação (CPF + nascimento)
2. 💳 Consulta de limite de crédito
3. 📈 Solicitação de aumento de limite
4. 📝 Entrevista de crédito (recalcula score)
5. 💱 Cotação de câmbio (dólar, euro, libra...)

---
**Exemplos de mensagem:**
- "Quero ver meu limite de crédito"
- "Quero aumentar meu limite para R$ 15.000"
- "Qual o dólar hoje?"
- "Quanto está o euro?"
        """)

        st.divider()
        st.caption(f"Session ID: `{st.session_state.get('session_id', 'N/A')[:8]}...`")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _init_state()
    _renderizar_header()
    _renderizar_status()
    _renderizar_sidebar()

    st.divider()

    # Histórico de mensagens
    _renderizar_historico()

    # Mensagem de boas-vindas (apenas na primeira vez)
    _mensagem_boas_vindas()

    # Input do usuário
    if not st.session_state.encerrado:
        user_input = st.chat_input(
            "Digite sua mensagem...",
            disabled=st.session_state.encerrado,
        )
        if user_input:
            _processar_mensagem(user_input.strip())
    else:
        st.info("Sessão encerrada. Clique em **🔄 Nova sessão** para reiniciar.")


if __name__ == "__main__":
    main()
