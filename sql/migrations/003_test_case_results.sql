CREATE TABLE IF NOT EXISTS TestCaseResult (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(100) NOT NULL,
    test_case_id VARCHAR(100) NULL,
    node_id VARCHAR(255) NOT NULL,
    outcome VARCHAR(50) NOT NULL,
    duration_ms INT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tcr_run_id (run_id),
    INDEX idx_tcr_case_id (test_case_id),
    INDEX idx_tcr_outcome (outcome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
