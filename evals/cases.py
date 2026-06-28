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
            "O atendente autenticou Ana Oliveira com sucesso e perguntou em que "
            "pode ajudar. A resposta não deve conter colchetes, nomes de agentes, "
            "'equipe' ou qualquer metadado interno."
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
            "O atendente conduziu a entrevista financeira (uma pergunta por vez), "
            "comunicou o novo score calculado de forma transparente e perguntou se "
            "o cliente deseja tentar o aumento de limite novamente. Nenhuma tag ou "
            "metadado interno deve aparecer na resposta."
        ),
    ),
    EvalCase(
        name="cambio_dolar",
        prompts=["Oi", "12345678901", "15/05/1990", "Qual o dólar hoje?"],
        criteria=(
            "O atendente apresentou a cotação do dólar (compra, venda e variação) "
            "em valores plausíveis em Reais, sem expor tags, nomes de agentes ou "
            "metadados internos."
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
