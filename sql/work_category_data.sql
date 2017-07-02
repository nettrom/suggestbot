-- Format of the work_categories table used
-- to store article titles, overarching work
-- category (e.g. STUB, WIKIFY), and a flag
-- to signify we've seen the article in the last update
-- (articles that weren't seen will be removed)
DROP TABLE IF EXISTS svwiki_work_category_data;
CREATE TABLE svwiki_work_category_data (
       title VARCHAR(255) NOT NULL, -- article title
       category VARCHAR(32) NOT NULL, -- work category
       seen BIT(1) DEFAULT 1, -- seen article in last update?
       PRIMARY KEY (title, category),
       KEY (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE utf8_bin;

CREATE TABLE enwiki_work_category_data LIKE svwiki_work_category_data;
CREATE TABLE fawiki_work_category_data LIKE svwiki_work_category_data;
CREATE TABLE frwiki_work_category_data LIKE svwiki_work_category_data;
CREATE TABLE nowiki_work_category_data LIKE svwiki_work_category_data;
CREATE TABLE ptwiki_work_category_data LIKE svwiki_work_category_data;
CREATE TABLE ruwiki_work_category_data LIKE svwiki_work_category_data;
