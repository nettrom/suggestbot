-- Format of the xxwiki_revisions table, used to store
-- revisions used by the coedit-recommender.
-- This is a simplified version of the MediaWiki revisions table,
-- simply because we currently only care about articles in namespace 0,
-- and don't store a lot of data.

DROP TABLE IF EXISTS enwiki_revisions;
CREATE TABLE enwiki_revisions (
       rev_id INT UNSIGNED NOT NULL AUTO_INCREMENT, -- revision id (might not be the same as Wikipedias, though)
       rev_title VARCHAR(255) BINARY NOT NULL, -- article title
       rev_user VARCHAR(255) BINARY NOT NULL, -- user who made the edit
       rev_timestamp DATETIME NOT NULL, -- when the revision was made
       rev_length INT UNSIGNED, -- length of this revision
       rev_delta_length INT, -- change in bytes from previous rev
       rev_is_identical BIT(1) DEFAULT 0, -- identical to a previous rev?
       rev_comment_is_revert BIT(1) DEFAULT 0, -- comment identifies a revert?
       rev_is_minor BIT(1) DEFAULT 0, -- minor edit?
       PRIMARY KEY(rev_id),
       KEY (rev_title),
       KEY (rev_user),
       KEY (rev_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

CREATE TABLE nowiki_revisions LIKE enwiki_revisions;
CREATE TABLE svwiki_revisions LIKE enwiki_revisions;
CREATE TABLE ptwiki_revisions LIKE enwiki_revisions;
CREATE TABLE ruwiki_revisions LIKE enwiki_revisions;
CREATE TABLE fawiki_revisions LIKE enwiki_revisions;
