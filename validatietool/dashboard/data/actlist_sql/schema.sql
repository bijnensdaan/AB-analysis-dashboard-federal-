-- Schrijven uitsluitend in een NIEUW lokaal cachebestand, nooit in PostgreSQL.
CREATE TABLE acts(act_id INTEGER PRIMARY KEY,numac TEXT,title TEXT,pub_date TEXT,act_form TEXT,
 level TEXT,entity TEXT,lang TEXT,url TEXT,numac_search TEXT,title_search TEXT);
CREATE TABLE verdicts(act_id INTEGER,run_id INTEGER,ab INTEGER,ab_scope TEXT,needs_review INTEGER,
 PRIMARY KEY(act_id,run_id));
CREATE TABLE readings(reading_id INTEGER PRIMARY KEY,act_id INTEGER,run_id INTEGER,model_slug TEXT,
 text_truncated INTEGER,failed INTEGER);
CREATE TABLE duties(duty_id INTEGER PRIMARY KEY,act_id INTEGER,run_id INTEGER,status TEXT,n_ab_claims INTEGER);
CREATE TABLE claims(obligation_id INTEGER PRIMARY KEY,act_id INTEGER,run_id INTEGER,quote TEXT,
 io_id TEXT,duty_bearer_kind TEXT,recipient_kind TEXT,ab_scope TEXT,frequency TEXT,cost_category TEXT,
 source_kind TEXT,is_new_here INTEGER,counts_as_ab INTEGER,quote_search TEXT);
CREATE TABLE duty_claims(duty_id INTEGER,obligation_id INTEGER,PRIMARY KEY(duty_id,obligation_id));
CREATE TABLE text_metadata(act_id INTEGER PRIMARY KEY,raw_chars INTEGER,disposition TEXT);
CREATE TABLE io_types(io_id TEXT PRIMARY KEY,name_short TEXT);
CREATE TABLE cost_categories(code TEXT PRIMARY KEY,name TEXT);
