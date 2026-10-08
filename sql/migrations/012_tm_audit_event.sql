-- Migration: 012_tm_audit_event
-- Creates the tamper-evident append-only audit event log with SHA-256 hash chaining.

CREATE TABLE IF NOT EXISTS TmAuditEvent (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_uuid VARCHAR(64) NOT NULL UNIQUE,
    event_type VARCHAR(64) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    actor_email VARCHAR(255) NOT NULL,
    payload_json TEXT NOT NULL,
    prev_hash VARCHAR(64) NOT NULL,
    event_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tm_audit_entity (entity_type, entity_id),
    INDEX idx_tm_audit_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
