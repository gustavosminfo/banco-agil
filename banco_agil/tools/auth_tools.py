"""
banco_agil/tools/auth_tools.py
Ferramentas de autenticação do Agente de Triagem.
Lê clientes.csv e valida CPF + data de nascimento.
"""

import re
from typing import Optional
import pandas as pd
from agno.run import RunContext
from banco_agil.config import CLIENTES_CSV, MAX_AUTH_ATTEMPTS


def _normalizar_cpf(cpf: str) -> str:
    """Remove pontuação e espaços do CPF, retorna apenas dígitos."""
    return re.sub(r"\D", "", cpf.strip())


def _mascarar_cpf(cpf: str) -> str:
    """Mascara um CPF (já normalizado ou não) para logging seguro — nunca
    logar CPF em texto puro."""
    digitos = _normalizar_cpf(cpf or "")
    if len(digitos) != 11:
        return "***"
    return f"***.***.**{digitos[-3:-2]}-{digitos[-2:]}"


def _normalizar_data(data: str) -> str:
    """
    Aceita datas em vários formatos e normaliza para YYYY-MM-DD.
    Exemplos: '15/05/1990', '15-05-1990', '1990-05-15', '15 de maio de 1990'.
    """
    data = data.strip()
    # Formato ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", data):
        return data
    # Formato BR dd/mm/aaaa ou dd-mm-aaaa
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", data)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # Retorna como veio (o LLM deve solicitar novo formato em caso de erro)
    return data


def _incrementar_tentativas(run_context: Optional[RunContext]) -> None:
    """Incrementa tentativas_auth em session_state e encerra a sessão se
    atingir MAX_AUTH_ATTEMPTS — mesma regra descrita nas instruções do
    coordenador (banco_agil/team.py), mas aplicada de verdade aqui."""
    if run_context is None:
        return
    if run_context.session_state is None:
        run_context.session_state = {}
    tentativas = run_context.session_state.get("tentativas_auth", 0) + 1
    run_context.session_state["tentativas_auth"] = tentativas
    if tentativas >= MAX_AUTH_ATTEMPTS:
        run_context.session_state["encerrado"] = True


def autenticar_cliente(cpf: str, data_nascimento: str, run_context: Optional[RunContext] = None) -> dict:
    """
    Valida CPF e data de nascimento contra a base de clientes (clientes.csv).

    Args:
        cpf: CPF do cliente (com ou sem pontuação).
        data_nascimento: Data de nascimento em qualquer formato legível.
        run_context: Injetado pelo Agno — usado para persistir o resultado da
            autenticação em session_state. Mutações de session_state só são
            persistidas quando feitas via run_context dentro de uma tool;
            instruções de texto pedindo ao coordenador para "definir
            session_state['autenticado'] = True" ao ver uma tag [AUTH_OK]
            NÃO mutam o estado real — o LLM não tem como executar essa
            atribuição, só narrar que a fez. Isso nunca causou problema
            visível até as ferramentas de crédito/entrevista passarem a
            checar team.session_state['autenticado'] de verdade
            (_verificar_autorizacao) — bug real observado em produção no
            canal WhatsApp: aumento de limite aprovado pelo score, mas
            bloqueado por "sessão não autenticada" mesmo após [AUTH_OK].

    Returns:
        dict com chaves:
            - sucesso (bool): True se autenticado.
            - mensagem (str): Mensagem para exibir ao cliente.
            - dados_cliente (dict | None): {nome, score, limite_credito} se autenticado.
    """
    try:
        df = pd.read_csv(CLIENTES_CSV, dtype={"cpf": str})
    except FileNotFoundError:
        return {
            "sucesso": False,
            "mensagem": "Base de clientes indisponível. Tente novamente em instantes.",
            "dados_cliente": None,
        }

    cpf_norm  = _normalizar_cpf(cpf)
    data_norm = _normalizar_data(data_nascimento)

    # CPF inválido (deve ter 11 dígitos)
    if len(cpf_norm) != 11:
        return {
            "sucesso": False,
            "mensagem": "CPF inválido. Informe os 11 dígitos.",
            "dados_cliente": None,
        }

    df["cpf"] = df["cpf"].apply(_normalizar_cpf)
    linha = df[df["cpf"] == cpf_norm]

    if linha.empty:
        _incrementar_tentativas(run_context)
        return {
            "sucesso": False,
            "mensagem": "Dados não encontrados. Verifique as informações e tente novamente.",
            "dados_cliente": None,
        }

    data_na_base = str(linha.iloc[0]["data_nascimento"]).strip()
    if data_na_base != data_norm:
        _incrementar_tentativas(run_context)
        return {
            "sucesso": False,
            "mensagem": "Dados não conferem. Verifique a data de nascimento.",
            "dados_cliente": None,
        }

    cliente = linha.iloc[0]

    if run_context is not None:
        if run_context.session_state is None:
            run_context.session_state = {}
        run_context.session_state["autenticado"]     = True
        run_context.session_state["cpf"]              = cpf_norm
        run_context.session_state["nome"]              = str(cliente["nome"])
        run_context.session_state["score"]             = int(cliente["score"])
        run_context.session_state["limite_credito"]    = float(cliente["limite_credito"])
        run_context.session_state["tentativas_auth"]   = 0

    return {
        "sucesso": True,
        "mensagem": f"Autenticação realizada com sucesso. Bem-vindo(a), {cliente['nome']}!",
        "dados_cliente": {
            "cpf":           cpf_norm,
            "nome":          str(cliente["nome"]),
            "score":         int(cliente["score"]),
            "limite_credito": float(cliente["limite_credito"]),
        },
    }


def buscar_dados_cliente(cpf: str) -> Optional[dict]:
    """
    Retorna os dados atualizados de um cliente a partir do CPF.
    Útil após atualização de score para refrescar o contexto.

    Args:
        cpf: CPF do cliente (apenas dígitos).

    Returns:
        dict com {cpf, nome, score, limite_credito} ou None se não encontrado.
    """
    try:
        df = pd.read_csv(CLIENTES_CSV, dtype={"cpf": str})
    except FileNotFoundError:
        return None

    df["cpf"] = df["cpf"].apply(_normalizar_cpf)
    linha = df[df["cpf"] == _normalizar_cpf(cpf)]

    if linha.empty:
        return None

    c = linha.iloc[0]
    return {
        "cpf":           _normalizar_cpf(cpf),
        "nome":          str(c["nome"]),
        "score":         int(c["score"]),
        "limite_credito": float(c["limite_credito"]),
    }
