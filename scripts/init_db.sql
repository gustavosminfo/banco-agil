-- Habilita a extensão pgvector usada pelo AgentOS para knowledge/embeddings.
CREATE EXTENSION IF NOT EXISTS vector;

-- Idempotência do canal WhatsApp (Kapso): evita reprocessar/reresponder a
-- mesma mensagem em caso de retry de webhook. Nota: este arquivo só roda
-- automaticamente no Postgres local via docker-compose
-- (docker-entrypoint-initdb.d) — no Railway (Postgres gerenciado) a tabela
-- é criada de forma lazy (CREATE TABLE IF NOT EXISTS) pelo próprio código em
-- banco_agil/channels/kapso_processing.py, então nenhuma migração manual é
-- necessária em produção.
CREATE TABLE IF NOT EXISTS kapso_webhook_events (
    message_id  TEXT PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
