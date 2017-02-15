-- Article improvement task table
USE s51172__tasks;
DROP TABLE IF EXISTS tasks_v1_p;
CREATE TABLE tasks_v1_p (
     lang VARCHAR(12) NOT NULL,
     page_id INT(8) UNSIGNED NOT NULL, -- page ID
     category VARCHAR(32) NOT NULL, -- work category
     seen BIT(1) DEFAULT 1, -- seen this page in last update?
     PRIMARY KEY (lang, page_id, category),
     KEY (lang, category)
) ENGINE=InnoDB;
