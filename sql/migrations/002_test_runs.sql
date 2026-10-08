CREATE TABLE IF NOT EXISTS TestRun (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(100) NOT NULL UNIQUE,
    job_name VARCHAR(150) NOT NULL,
    environment VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    triggered_by VARCHAR(100) NOT NULL,
    image_digest VARCHAR(150) NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Running',
    INDEX idx_test_run_env (environment),
    INDEX idx_test_run_job (job_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
