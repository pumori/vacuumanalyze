# vacuumanalyze
automate vacuum analyze on PostgreSQL table

#check vacuum analyze stats
select schemaname, relname, n_live_tup, n_dead_tup, last_vacuum, last_vacuum from pg_stat_user_tables;

#activate virtual environment
# Navigate to your project directory
cd ~/postgres-vacuum


# adding control table

keshav=# insert into maintenance.vacuum_control values ('public','posts','active');
INSERT 0 1
keshav=# select * from maintenance.vacuum_control;
 table_schema | table_name | status |        last_vacuum         
--------------+------------+--------+----------------------------
 public       | users      | active | 2025-02-23 16:53:55.452436
 public       | posts      | active | 
(2 rows)


#running the vacuum analyze python script
# Activate the virtual environment
source venv/bin/activate
python vacuum_analyzer.py

### successful run
(venv) keshav@Bijayas-MacBook-Air-2022 postgres-vacuum % python vacuum_analyzer.py -d
2025-02-23 16:56:59,281 - INFO - Connected to keshav
2025-02-23 16:56:59,288 - INFO - Skipping public.users - vacuumed recently
2025-02-23 16:56:59,343 - INFO - Vacuuming public.posts...
2025-02-23 16:57:02,911 - INFO - Successfully processed public.posts
2025-02-23 16:57:02,912 - INFO - Processing complete. Success: 1, Failures: 0

================ table scripts ==========
-- Create maintenance schema
CREATE SCHEMA maintenance;

-- Create vacuum control table
CREATE TABLE maintenance.vacuum_control (
    table_schema VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    last_vacuum TIMESTAMP,
    status VARCHAR(50) DEFAULT 'active',
    PRIMARY KEY (table_schema, table_name)
);

-- Create vacuum stats table
CREATE TABLE maintenance.vacuum_stats (
    id SERIAL PRIMARY KEY,
    table_schema VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    dead_tuples_before BIGINT,
    dead_tuples_after BIGINT,
    size_before VARCHAR(50),
    size_after VARCHAR(50),
    operation_time TIMESTAMP DEFAULT NOW()
);

-- Create logging account
CREATE ROLE logger WITH LOGIN PASSWORD 'logger_password';
GRANT CONNECT ON DATABASE your_database TO logger;
GRANT USAGE ON SCHEMA maintenance TO logger;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA maintenance TO logger;

-- Grant necessary privileges to the vacuum user
GRANT CONNECT ON DATABASE your_database TO your_vacuum_user;
GRANT USAGE ON SCHEMA maintenance TO your_vacuum_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA maintenance TO your_vacuum_user;
GRANT VACUUM ON ALL TABLES IN SCHEMA your_schema TO your_vacuum_user;
