-- SQL definition of the table used for caching
-- popularity and quality data when updating
-- Template:Opentask-short on en-WP
DROP TABLE IF EXISTS opentask_short;
CREATE TABLE opentask_short (
       page_id INT UNSIGNED NOT NULL,
       rev_id INT UNSIGNED NOT NULL DEFAULT 0, -- rev id we got quality data for
       assessed_class VARCHAR(64) BINARY NULL, -- assessed class (talk page templates)
       predicted_class ENUM('Stub', 'Start', 'C', 'B', 'A', 'GA', 'FA') NULL, -- predicted class
       quality ENUM('Low', 'Medium', 'High') NULL, -- SuggestBot's corresponding quality class

       pop_timestamp BINARY(14) NULL, -- time when we got pop data
       popcount INT NULL, -- avg # of views past 14 days (floored)
       popularity ENUM('Low', 'Medium', 'High') NULL, -- SuggestBot's corresponding popularity class

       PRIMARY KEY(page_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
