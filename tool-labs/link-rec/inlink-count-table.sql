-- FIXME: Remove this line before committing to bitbucket
USE p50380g50553__ilc;

-- Format of the inlink count table used by links-server.py
CREATE TABLE enwiki_inlinkcounts (
       ilc_page_id INT(8) UNSIGNED NOT NULL PRIMARY KEY, -- page ID
       ilc_numlinks INTEGER UNSIGNED DEFAULT '0' -- # of inlinks (obviously [0,...]
) ENGINE=InnoDB

CREATE TABLE inlinkcount_updates (
       ilcu_lang VARCHAR(16) NOT NULL PRIMARY KEY, -- language code
       ilcu_timestamp DATETIME, -- timestamp of last edited page read
       ilcu_update_running BIT(1) DEFAULT 0 -- set if this wiki is currently being updated
) ENGINE=InnoDB

-- Insert default values for en on s1
INSERT INTO inlinkcount_updates
VALUES ('en', NULL)

-- Insert default values for no, sv, and pt on that shard
INSERT INTO inlinkcount_updates
VALUES ('no', NULL), ('sv', NULL), ('pt', NULL);
