#vacuum analyze automation on feb 23
import os
import logging
import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from logging.handlers import TimedRotatingFileHandler

# Load environment variables from a .env file
load_dotenv()

# Configuration
LOG_DIR = os.path.expanduser("~/postgres-vacuum/logs")
INVENTORY_FILE = "db_inventory.csv"
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

class VacuumAnalyzer:
    def __init__(self):
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

    def setup_logging(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, "vacuum_analyze.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                TimedRotatingFileHandler(
                    log_file,
                    when="midnight",
                    interval=1,
                    backupCount=7
                ),
                logging.StreamHandler()
            ]
        )

    def send_email(self, subject, body):
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")

    def check_locks(self, conn, schema, table):
        query = """
            SELECT COUNT(*) AS lock_count
            FROM pg_locks l
            JOIN pg_stat_activity a ON l.pid = a.pid
            WHERE l.relation = %s::regclass
              AND a.state = 'active'
        """
        try:
            with conn.cursor() as cur:
                cur.execute(query, (f"{schema}.{table}",))
                return cur.fetchone()[0] > 0
        except Exception as e:
            self.logger.error(f"Lock check failed: {str(e)}")
            return True  # Assume locked if check fails

    def process_table(self, main_conn, schema, table):
        try:
            # Check last vacuum time from control table
            with main_conn.cursor() as cur:
                cur.execute("""
                    SELECT last_vacuum 
                    FROM maintenance.vacuum_control
                    WHERE table_schema = %s AND table_name = %s
                """, (schema, table))
                result = cur.fetchone()
                last_vacuum = result[0] if result else None

            if last_vacuum and last_vacuum > datetime.now() - timedelta(days=1):
                self.logger.info(f"Skipping {schema}.{table} - vacuumed recently")
                return

            # Get pre-vacuum stats
            with main_conn.cursor() as cur:
                cur.execute("""
                    SELECT n_dead_tup, 
                           pg_size_pretty(pg_total_relation_size(%s))
                    FROM pg_stat_user_tables
                    WHERE schemaname = %s AND relname = %s
                """, (f"{schema}.{table}", schema, table))
                pre_stats = cur.fetchone()

            # Create dedicated connection for VACUUM so it runs outside a transaction
            vacuum_conn = psycopg2.connect(
                host=main_conn.info.host,
                dbname=main_conn.info.dbname,
                user=main_conn.info.user,
                password=main_conn.info.password,
                port=main_conn.info.port
            )
            vacuum_conn.autocommit = True  # Critical for VACUUM
            with vacuum_conn.cursor() as cur:
                self.logger.info(f"Vacuuming {schema}.{table}...")
                cur.execute(
                    sql.SQL("VACUUM (VERBOSE, ANALYZE) {}.{}").format(
                        sql.Identifier(schema),
                        sql.Identifier(table)
                    )
                )
            vacuum_conn.close()

            # Update control table with the current time
            with main_conn.cursor() as cur:
                cur.execute("""
                    UPDATE maintenance.vacuum_control
                    SET last_vacuum = NOW()
                    WHERE table_schema = %s AND table_name = %s
                """, (schema, table))
                main_conn.commit()

            # Get post-vacuum stats
            with main_conn.cursor() as cur:
                cur.execute("""
                    SELECT n_dead_tup, 
                           pg_size_pretty(pg_total_relation_size(%s))
                    FROM pg_stat_user_tables
                    WHERE schemaname = %s AND relname = %s
                """, (f"{schema}.{table}", schema, table))
                post_stats = cur.fetchone()

            # Log the stats in the vacuum_stats table
            with main_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO maintenance.vacuum_stats 
                    (table_schema, table_name, operation, 
                     dead_tuples_before, dead_tuples_after,
                     size_before, size_after)
                    VALUES (%s, %s, 'VACUUM ANALYZE', 
                            %s, %s, %s, %s)
                """, (schema, table, pre_stats[0], post_stats[0],
                      pre_stats[1], post_stats[1]))
                main_conn.commit()

            self.logger.info(f"Successfully processed {schema}.{table}")

        except Exception as e:
            self.logger.error(f"Error processing {schema}.{table}: {str(e)}")
            main_conn.rollback()
            raise

    def process_database(self, db_config):
        try:
            conn = psycopg2.connect(
                host=db_config['host'],
                dbname=db_config['dbname'],
                user=db_config['user'],
                password=db_config['password'],
                port=db_config['port']
            )
            self.logger.info(f"Connected to {db_config['dbname']}")

            # Retrieve tables to process
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_schema, table_name
                    FROM maintenance.vacuum_control
                    WHERE status = 'active'
                """)
                tables = cur.fetchall()

            for schema, table in tables:
                if self.check_locks(conn, schema, table):
                    self.logger.info(f"Skipping {schema}.{table} - locked")
                    continue
                try:
                    self.process_table(conn, schema, table)
                except Exception as e:
                    self.logger.error(f"Skipping {schema}.{table} due to error")
                    continue

            conn.close()
            return True

        except Exception as e:
            self.logger.error(f"Database connection failed: {str(e)}")
            return False

    def run(self):
        success_count = 0
        failure_count = 0

        try:
            with open(INVENTORY_FILE, 'r') as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.strip().split(',')
                    if len(parts) != 5:
                        self.logger.error(f"Invalid line format: {line}")
                        continue

                    db_config = {
                        'host': parts[0],
                        'dbname': parts[1],
                        'port': int(parts[2]),
                        'user': parts[3],
                        'password': parts[4]
                    }

                    if self.process_database(db_config):
                        success_count += 1
                    else:
                        failure_count += 1

            summary = f"Processing complete. Success: {success_count}, Failures: {failure_count}"
            self.logger.info(summary)
            self.send_email("Vacuum/Analyze Completed", summary)

        except Exception as e:
            error_msg = f"Critical failure: {str(e)}"
            self.logger.error(error_msg)
            self.send_email("Vacuum/Analyze Failed", error_msg)

if __name__ == "__main__":
    analyzer = VacuumAnalyzer()
    analyzer.run()

