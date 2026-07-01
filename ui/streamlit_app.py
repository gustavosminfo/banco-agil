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

import httpx
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
    if "processando" not in st.session_state:
        st.session_state.processando     = False
    if "pending_message" not in st.session_state:
        st.session_state.pending_message = None


def _resetar_sessao() -> None:
    """Reinicia completamente a sessão de atendimento."""
    for key in ["session_id", "client", "messages",
                "autenticado", "nome_cliente",
                "tentativas_auth", "encerrado",
                "processando", "pending_message"]:
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

def _texto_seguro_para_exibir(buffer_raw: str) -> str:
    """Limpa as tags já completas no buffer e oculta uma tag em formação no
    final (ex.: "...obrigado! [AUTH_O") até que ela termine ou se confirme
    como texto normal — evita "piscar" a tag por uma fração de segundo
    enquanto ela ainda está sendo transmitida em pedaços.
    """
    ultimo_abre = buffer_raw.rfind("[")
    if ultimo_abre != -1 and "]" not in buffer_raw[ultimo_abre:]:
        buffer_raw = buffer_raw[:ultimo_abre]
    return limpar_tags_da_resposta(buffer_raw)


def _processar_mensagem(user_input: str) -> None:
    """Fase 1 do two-phase submit: registra a mensagem e dispara rerun com input bloqueado.

    O chat_input do Streamlit é renderizado antes desta função ser chamada, então
    setar processando=True aqui não desabilita o widget na run atual — o usuário
    ainda poderia enviar outra mensagem e o Streamlit interromperia o streaming.
    A solução: armazenar a mensagem em pending_message, setar processando=True e
    chamar st.rerun(). Na run seguinte o chat_input já nasce desabilitado.
    """
    st.session_state.messages.append(("user", user_input))
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)
    st.session_state.pending_message = user_input
    st.session_state.processando = True
    st.rerun()


def _executar_streaming(user_input: str) -> None:
    """Fase 2 do two-phase submit: executa o streaming com o input já desabilitado.

    Esta função só é chamada em runs onde processando=True foi setado na run
    anterior, garantindo que o chat_input foi renderizado como disabled=True e
    o Streamlit não pode interromper esta execução por novo input do usuário.
    """
    if st.session_state.encerrado:
        msg_enc = "Esta sessão foi encerrada. Clique em **🔄 Nova sessão** para reiniciar."
        st.session_state.messages.append(("assistant", msg_enc))
        with st.chat_message("assistant", avatar="🏦"):
            st.markdown(msg_enc)
        st.session_state.processando = False
        st.session_state.pending_message = None
        return

    with st.chat_message("assistant", avatar="🏦"):
        placeholder = st.empty()
        placeholder.markdown("_Pensando..._")
        resposta_raw = ""
        try:
            for chunk in st.session_state.client.run_stream(
                team_id=TEAM_ID,
                message=user_input,
                session_id=st.session_state.session_id,
                user_id=st.session_state.get("cpf_cliente"),
            ):
                resposta_raw += chunk
                texto_visivel = _texto_seguro_para_exibir(resposta_raw)
                if texto_visivel.strip():
                    placeholder.markdown(texto_visivel + " ▌")
        except httpx.TimeoutException:
            resposta_raw = (
                "⏱️ O atendimento está demorando mais que o esperado. "
                "Tente novamente em instantes."
            )
        except Exception as exc:
            resposta_raw = (
                "Desculpe, tivemos uma instabilidade temporária. "
                f"Tente novamente em instantes. ({type(exc).__name__})"
            )
        finally:
            st.session_state.processando = False
            st.session_state.pending_message = None

        _processar_tags_resposta(resposta_raw)
        resposta_limpa = limpar_tags_da_resposta(resposta_raw)
        placeholder.markdown(resposta_limpa)

    st.session_state.messages.append(("assistant", resposta_limpa))
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
        st.header("📋 Guia de atendimento")
        st.markdown("""
**Fluxos disponíveis:**
1. 🔐 Autenticação (CPF + data de nascimento)
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

    # Fase 2 do two-phase submit: executa o streaming se há mensagem pendente.
    # Não há chat_input renderizado antes deste bloco, então o Streamlit não
    # pode interromper este run por submit do usuário.
    if st.session_state.pending_message and st.session_state.processando:
        _executar_streaming(st.session_state.pending_message)
        # Não há return aqui: após o streaming o script continua e renderiza
        # o chat_input abaixo, tornando o campo visível novamente.

    # Input do usuário (fase 1: captura e dispara rerun)
    if not st.session_state.encerrado:
        user_input = st.chat_input(
            "Digite sua mensagem...",
            disabled=st.session_state.encerrado or st.session_state.processando,
        )
        # Ignora qualquer input capturado na janela de race entre o submit e
        # o st.rerun() que ainda não desabilitou o campo.
        if user_input and not st.session_state.processando:
            _processar_mensagem(user_input.strip())
    else:
        st.info("Sessão encerrada. Clique em **🔄 Nova sessão** para reiniciar.")


if __name__ == "__main__":
    main()
