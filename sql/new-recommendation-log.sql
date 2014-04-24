-- New and improved recommendation log tables

CREATE TABLE user_recommendations (
       recsetid INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
       lang VARCHAR(16) NOT NULL,
       username VARCHAR(255) BINARY NOT NULL,
       rectime TIMESTAMP NOT NULL,
       KEY(lang, username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE utf8_bin;

CREATE TABLE recommendation_log_new (
       recsetid INT UNSIGNED NOT NULL,
       title VARCHAR(255) BINARY NOT NULL,
       category VARCHAR(16) BINARY NOT NULL,
       rank INT NOT NULL, -- number of rec within a given category
       rec_source VARCHAR(16) NOT NULL, -- which recommender engine it matched
       rec_rank INT NOT NULL, -- rank in the rec engine's list of candidates
       popcount INT, -- number of views/day for past 14 days
       popularity ENUM('Low', 'Medium', 'High'),
       quality ENUM('Low', 'Medium', 'High'),
       assessed_class VARCHAR(64), -- assessed class from talk page
       predicted_class ENUM('Stub', 'Start', 'C', 'B', 'A', 'GA', 'FA'),
       work_suggestions VARCHAR(255) BINARY,
       KEY(recsetid),
       CONSTRAINT FOREIGN KEY (recsetid) REFERENCES user_recommendations(recsetid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE utf8_bin;
