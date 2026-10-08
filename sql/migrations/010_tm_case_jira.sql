CREATE TABLE IF NOT EXISTS TmCaseJira (
    id INT AUTO_INCREMENT PRIMARY KEY,
    case_id VARCHAR(100) NOT NULL,
    jira_key VARCHAR(50) NOT NULL,
    link_kind VARCHAR(50) NOT NULL DEFAULT 'covers',
    linked_by VARCHAR(100) NOT NULL DEFAULT 'system',
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP NULL DEFAULT NULL,
    UNIQUE KEY uq_case_jira (case_id, jira_key),
    INDEX idx_tm_case_jira_key (jira_key),
    INDEX idx_tm_case_jira_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
