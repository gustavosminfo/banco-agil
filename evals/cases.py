"""
evals/cases.py
Casos de eval (AgentAsJudgeEval) cobrindo os fluxos críticos do Banco Ágil
(SDD §16.2). Cada caso é uma sequência de mensagens de um cliente simulado;
o critério é avaliado pelo juiz contra a transcrição completa da conversa.
"""

from dataclasses import dataclass


@dataclass
class EvalCase:
    name: str
    prompts: list[str]
    criteria: str


CASES: list[EvalCase] = [
    EvalCase(
        name="auth_happy_path",
        prompts=["Oi", "12345678901", "15/05/1990"],
        criteria=(
            "APROVADO se: o atendente confirmou a identidade de Ana Oliveira e "
            "perguntou como pode ajudar. "
            "REPROVADO apenas se a resposta contiver literalmente colchetes com tags "
            "técnicas como '[AUTH_OK', '[AUTH_FAIL', '[ROUTE|', '[ENCERRADO]', "
            "ou nomes técnicos de agentes internos como 'Agente de Triagem', "
            "'Agente de Crédito', 'Agente de Câmbio', ou a palavra isolada 'equipe' "
            "referindo-se à arquitetura interna. "
            "NÃO reprovar por: mencionar o nome do banco, o nome da cliente, "
            "listar serviços disponíveis, ou usar frases de confirmação de autenticação."
        ),
    ),
    EvalCase(
        name="aumento_aprovado",
        prompts=[
            "Oi",
            "12345678901",
            "15/05/1990",
            "Quero aumentar meu limite para R$ 9.000",
        ],
        criteria=(
            "Ana Oliveira (score 720) solicitou aumento para R$ 9.000, dentro do "
            "limite máximo permitido (R$ 10.000). O atendente deve confirmar a "
            "aprovação do novo limite, sem expor tags ou metadados internos."
        ),
    ),
    EvalCase(
        name="rejeicao_oferece_entrevista",
        prompts=[
            "Oi",
            "98765432100",
            "23/11/1985",
            "Quero aumentar meu limite para R$ 5.000",
        ],
        criteria=(
            "Bruno Santos (score 450, limite máximo R$ 2.000) pediu aumento para "
            "R$ 5.000. O atendente deve explicar que o score atual não permite esse "
            "valor e oferecer uma entrevista de crédito para tentar recalcular o "
            "score, sem expor tags ou metadados internos."
        ),
    ),
    EvalCase(
        name="entrevista_recalcula_score",
        prompts=[
            "Oi",
            "98765432100",
            "23/11/1985",
            "Quero aumentar meu limite para R$ 5.000",
            "Sim, quero fazer a entrevista",
            "5000",
            "formal",
            "1500",
            "1",
            "não",
        ],
        criteria=(
            "APROVADO se: as respostas do atendente mostram que ele conduziu uma "
            "entrevista financeira (perguntou renda, vínculo empregatício, despesas, "
            "dependentes e dívidas — uma pergunta por vez), comunicou um novo score "
            "calculado numericamente (ex.: 'score subiu para X'), e perguntou se o "
            "cliente quer tentar o aumento de limite novamente. "
            "REPROVADO apenas se as respostas do atendente contiverem literalmente "
            "colchetes com tags técnicas como '[AUTH_OK', '[ROUTE|', '[ENCERRADO]', "
            "ou nomes técnicos de agentes como 'Agente de Triagem', 'Agente de "
            "Entrevista', ou a palavra isolada 'equipe' referindo-se à arquitetura. "
            "IGNORAR completamente as linhas que começam com 'Cliente:' — elas são "
            "as mensagens enviadas pelo usuário, não fazem parte da resposta do "
            "atendente e não devem influenciar a avaliação."
        ),
    ),
    EvalCase(
        name="cambio_dolar",
        prompts=["Oi", "12345678901", "15/05/1990", "Qual o dólar hoje?"],
        criteria=(
            "APROVADO se: o atendente apresentou a cotação do dólar americano com "
            "valores de compra e/ou venda em Reais (ex.: R$ 5,xx) e pelo menos uma "
            "indicação de variação ou horário. "
            "REPROVADO apenas se as respostas do atendente contiverem literalmente "
            "colchetes com tags técnicas como '[AUTH_OK', '[ROUTE|', '[ENCERRADO]', "
            "ou nomes técnicos de agentes como 'Agente de Câmbio', 'Agente de "
            "Triagem', ou a palavra isolada 'equipe' referindo-se à arquitetura. "
            "NÃO reprovar por: mencionar o nome do banco, o nome da cliente "
            "autenticada (Ana Oliveira), solicitar CPF e data de nascimento para "
            "autenticação, ou listar serviços disponíveis."
        ),
    ),
    EvalCase(
        name="bloqueio_3_tentativas",
        prompts=[
            "Oi",
            "00000000000",
            "01/01/2000",
            "00000000000",
            "01/01/2000",
            "00000000000",
            "01/01/2000",
        ],
        criteria=(
            "Após 3 tentativas de autenticação com dados inválidos, o atendente "
            "encerrou o atendimento educadamente informando o bloqueio por "
            "segurança, sem expor tags ou metadados internos."
        ),
    ),
]
