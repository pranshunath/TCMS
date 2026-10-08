CREATE TABLE IF NOT EXISTS TriggerRunHistory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(100) NOT NULL UNIQUE,
    job_name VARCHAR(150) NOT NULL,
    environment VARCHAR(50) NOT NULL,
    triggered_by VARCHAR(100) NOT NULL,
    test_type VARCHAR(50) NOT NULL DEFAULT 'api',
    image_digest VARCHAR(150) NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Triggered',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trh_run_id (run_id),
    INDEX idx_trh_env (environment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
