-- Article improvement task table
USE s51172__tasks;
DROP TABLE IF EXISTS enwiki_tasks;
CREATE TABLE enwiki_tasks (
     page_id INT(8) UNSIGNED NOT NULL, -- page ID
     category VARCHAR(32) NOT NULL, -- work category
     seen BIT(1) DEFAULT 1, -- seen this page in last update?
     PRIMARY KEY (page_id, category),
     KEY (category)
) ENGINE=InnoDB;

