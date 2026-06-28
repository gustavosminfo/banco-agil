#!/bin/bash
# scripts/railway_up.sh
#
# Deploy do Banco Ágil no Railway (SDD §17.2, TASK-016).
#
# Pré-requisitos:
#   - Railway CLI instalado: npm i -g @railway/cli  (https://docs.railway.app/develop/cli)
#   - .env preenchido na raiz do projeto (copie de example.env)
#   - keys/jwt_public.pem gerado via scripts/generate_jwt_keys.sh (opcional,
#     só necessário para conectar o os.agno.com em modo "Live")
#
# Uso:
#   bash scripts/railway_up.sh
#
# O script é interativo nos passos que exigem login/confirmação do Railway.
# Os nomes exatos de flags podem variar entre versões do `railway` CLI —
# confira `railway --help` se algum comando falhar.

set -e

cd "$(dirname "$0")/.."

if ! command -v railway &> /dev/null; then
  echo "Railway CLI não encontrado. Instale com: npm i -g @railway/cli"
  exit 1
fi

if [ ! -f .env ]; then
  echo ".env não encontrado. Copie example.env para .env e preencha antes de continuar."
  exit 1
fi

echo "== 1. Login no Railway =="
railway login

echo "== 2. Vincular/criar o projeto =="
railway init --name banco-agil || railway link

echo "== 3. Provisionar Postgres =="
# Cria um serviço Postgres no projeto. O Railway expõe a connection string
# como DATABASE_URL no próprio serviço Postgres — referenciamos essa
# variável no serviço da aplicação no passo 5 (banco_agil/config.py já
# normaliza o dialeto para psycopg3 automaticamente).
railway add --database postgres

echo "== 4. Habilitar pgvector =="
echo "Rode manualmente, uma vez, contra o Postgres provisionado:"
echo "  railway connect postgres"
echo "  -- dentro do psql:"
echo "  CREATE EXTENSION IF NOT EXISTS vector;"
read -p "Pressione ENTER após habilitar a extensão pgvector... "

echo "== 5. Configurar variáveis de ambiente da aplicação =="
railway variables set \
  DEEPINFRA_API_KEY="$(grep -E '^DEEPINFRA_API_KEY=' .env | cut -d= -f2-)" \
  COORDINATOR_MODEL_ID="$(grep -E '^COORDINATOR_MODEL_ID=' .env | cut -d= -f2-)" \
  SPECIALIST_MODEL_ID="$(grep -E '^SPECIALIST_MODEL_ID=' .env | cut -d= -f2-)" \
  APP_ENV=production \
  LOG_LEVEL=INFO \
  AGNO_TELEMETRY=false \
  DB_URL='${{Postgres.DATABASE_URL}}'

if [ -f keys/jwt_public.pem ]; then
  echo "== 5b. Configurar JWT_VERIFICATION_KEY (para conexão Live com os.agno.com) =="
  railway variables set JWT_VERIFICATION_KEY="$(cat keys/jwt_public.pem)"
else
  echo "Aviso: keys/jwt_public.pem não encontrado — pulei JWT_VERIFICATION_KEY."
  echo "Rode scripts/generate_jwt_keys.sh se for conectar o os.agno.com depois."
fi

echo "== 6. Deploy =="
railway up

echo
echo "== Deploy concluído =="
echo "Domínio público: $(railway domain 2>/dev/null || echo '(rode: railway domain)')"
echo "Verifique com: curl https://<seu-domínio>/health"
