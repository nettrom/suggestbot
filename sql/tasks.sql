-- NOTE: the database only exists on c3.labsdb, it does not exist               
-- on other servers, thus requiring us to connect to that specific server.      

-- Create the database if it does not exist.                                    
CREATE DATABASE IF NOT EXISTS s51172__tasks;

-- Article improvement task table                                               
DROP TABLE IF EXISTS tasks_p;
CREATE TABLE tasks_p (
     lang VARCHAR(12), -- language code                                         
     page_id INT(8) UNSIGNED NOT NULL, -- page ID                               
     category VARCHAR(32) NOT NULL, -- work category                            
     seen BIT(1) DEFAULT 1, -- seen this page in last update?                   
     PRIMARY KEY (lang, page_id, category),
     KEY (lang, category)
) ENGINE=InnoDB;
