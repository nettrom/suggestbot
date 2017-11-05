-- USE p50380g50553__ilc;
USE s51172__ilc_p;

-- Format of the inlink count table used by links-server.py
CREATE TABLE enwiki_inlinkcounts (
       ilc_page_id INT(8) UNSIGNED NOT NULL PRIMARY KEY, -- page ID
       ilc_numlinks INTEGER UNSIGNED DEFAULT 0, -- # of inlinks
       ilc_age TINYINT UNSIGNED DEFAULT 0 -- num days since last update
) ENGINE=InnoDB;

-- Create tables for all the other Wikipedias:
CREATE TABLE fawiki_inlinkcounts LIKE enwiki_inlinkcounts;
CREATE TABLE frwiki_inlinkcounts LIKE enwiki_inlinkcounts;
CREATE TABLE nowiki_inlinkcounts LIKE enwiki_inlinkcounts;
CREATE TABLE ptwiki_inlinkcounts LIKE enwiki_inlinkcounts;
CREATE TABLE ruwiki_inlinkcounts LIKE enwiki_inlinkcounts;
CREATE TABLE svwiki_inlinkcounts LIKE enwiki_inlinkcounts;

CREATE TABLE inlinkcount_updates (
       ilcu_lang VARCHAR(16) NOT NULL PRIMARY KEY, -- language code
       ilcu_timestamp DATETIME, -- timestamp of last edited page read
       ilcu_update_running TINYINT DEFAULT 0 -- set if this wiki is currently being updated
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Insert default values for all Wikipedias
INSERT INTO inlinkcount_updates
(ilcu_lang, ilcu_timestamp)
VALUES ('en', NULL),
       ('fa', NULL),
       ('fr', NULL),
       ('no', NULL),
       ('pt', NULL),
       ('ru', NULL),
       ('sv', NULL);




