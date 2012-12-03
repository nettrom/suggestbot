-- SQL definition of the table used for logging data
DROP TABLE IF EXISTS u_nettrom_opentask_log;
CREATE TABLE u_nettrom_opentask_log (
       page_selected DATETIME, -- time the page was selected
       page_title VARCHAR(255) BINARY NULL, -- page title
       page_len INT NULL, -- page length in bytes
       task_category VARCHAR(255) BINARY NOT NULL, -- task category id

       -- These only apply when we're oversampling
       assessed_class VARCHAR(64) BINARY NULL, -- assessed class (talk page templates)
       predicted_class ENUM('Stub', 'Start', 'C', 'B', 'A', 'GA', 'FA') NULL, -- predicted class
       popcount INT NULL, -- avg # of views past 14 days (floored)
       popularity ENUM('Low', 'Medium', 'High') NULL, -- SuggestBot's corresponding popularity class
       quality ENUM('Low', 'Medium', 'High') NULL, -- SuggestBot's corresponding quality class
       -- Which strategy was used to select this page?
       strategy ENUM('random', 'highpop', 'highqual', 'lowqual', 'maxlove') NULL,

       -- Indexes
       PRIMARY KEY (page_selected, page_title, task_category),
       KEY(page_title)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
