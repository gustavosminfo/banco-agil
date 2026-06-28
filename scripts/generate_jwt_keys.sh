#!/bin/bash
# scripts/generate_jwt_keys.sh
#
# Gera o par de chaves RSA usado para validar tokens JWT do os.agno.com
# contra o AgentOS hospedado no Railway (SDD §2.2 nota, TASK-017).
#
# Uso:
#   bash scripts/generate_jwt_keys.sh
#
# Saída:
#   keys/jwt_private.pem  — fica só com você, NUNCA suba para o Railway/git.
#   keys/jwt_public.pem   — conteúdo vai na env var JWT_VERIFICATION_KEY do Railway.

set -e

cd "$(dirname "$0")/.."
OUT_DIR="keys"
mkdir -p "$OUT_DIR"

PRIVATE_KEY="$OUT_DIR/jwt_private.pem"
PUBLIC_KEY="$OUT_DIR/jwt_public.pem"

if [ -f "$PRIVATE_KEY" ]; then
  echo "Já existe $PRIVATE_KEY — apague-o manualmente antes de gerar um novo par."
  exit 1
fi

openssl genrsa -out "$PRIVATE_KEY" 2048
openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"

chmod 600 "$PRIVATE_KEY"

echo
echo "Chaves geradas em $OUT_DIR/."
echo "Próximo passo: configure no Railway a variável JWT_VERIFICATION_KEY com o"
echo "conteúdo de $PUBLIC_KEY:"
echo
echo "  railway variables set JWT_VERIFICATION_KEY=\"\$(cat $PUBLIC_KEY)\""
echo
echo "A chave privada ($PRIVATE_KEY) NÃO é usada pelo AgentOS — guarde-a apenas"
echo "se for você mesmo a assinar os JWTs (ex.: testes locais sem os.agno.com)."
