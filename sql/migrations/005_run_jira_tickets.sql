CREATE TABLE IF NOT EXISTS RunJiraTickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(100) NOT NULL,
    jira_key VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rjt_run (run_id),
    INDEX idx_rjt_jira (jira_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
