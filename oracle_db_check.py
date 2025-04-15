import cx_Oracle
import pandas as pd
from datetime import datetime
import uuid
import sys
from pathlib import Path

# Configuration
DB_USER = "readonly_user"
DB_PASSWORD = "your_password"
DB_DSN = "localhost:1521/ORCL"
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

def get_db_connection():
    try:
        connection = cx_Oracle.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
        return connection
    except cx_Oracle.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def check_user_profiles(connection):
    cursor = connection.cursor()
    query = """
    SELECT u.username, u.profile, p.limit AS password_life_time, p.function
    FROM dba_users u
    LEFT JOIN dba_profiles p ON u.profile = p.profile
    WHERE p.resource_name = 'PASSWORD_LIFE_TIME'
    AND u.account_status = 'OPEN'
    """
    try:
        cursor.execute(query)
        results = cursor.fetchall()
        columns = ['USERNAME', 'PROFILE', 'PASSWORD_LIFE_TIME', 'VERIFICATION_FUNCTION']
        df = pd.DataFrame(results, columns=columns)
        return df
    except cx_Oracle.Error as e:
        print(f"Error executing query: {e}")
        return pd.DataFrame()
    finally:
        cursor.close()

def analyze_results(df):
    issues = []
    for _, row in df.iterrows():
        findings = []
        # Check password life time (170 days = 170)
        if row['PASSWORD_LIFE_TIME'] != '170':
            findings.append(f"Password life time is {row['PASSWORD_LIFE_TIME']} days, expected 170 days")
        # Check verification function
        if pd.isna(row['VERIFICATION_FUNCTION']) or row['VERIFICATION_FUNCTION'] == 'NULL':
            findings.append("No password verification function assigned")
        # Check profile
        if row['PROFILE'] != 'DBA_PROFILE':
            findings.append(f"Profile is {row['PROFILE']}, expected DBA_PROFILE")
        
        if findings:
            issues.append({
                'username': row['USERNAME'],
                'issues': "; ".join(findings),
                'recommendation': "Assign DBA_PROFILE with 170-day password expiry and complex password verification function"
            })
    return issues

def generate_html_report(issues):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = REPORT_DIR / f"oracle_security_check_{timestamp}.html"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Oracle Database Security Check Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            h1 {{ color: #333; }}
        </style>
    </head>
    <body>
        <h1>Oracle Database Security Check Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <table>
            <tr>
                <th>Username</th>
                <th>Issues Found</th>
                <th>Recommendation</th>
            </tr>
    """
    
    if not issues:
        html_content += "<tr><td colspan='3'>No issues found. All accounts compliant.</td></tr>"
    else:
        for issue in issues:
            html_content += f"""
            <tr>
                <td>{issue['username']}</td>
                <td>{issue['issues']}</td>
                <td>{issue['recommendation']}</td>
            </tr>
            """
    
    html_content += """
        </table>
    </body>
    </html>
    """
    
    with open(report_file, 'w') as f:
        f.write(html_content)
    return report_file

def main():
    connection = get_db_connection()
    try:
        # Check user profiles
        df = check_user_profiles(connection)
        if df.empty:
            print("No data retrieved from database")
            return
        
        # Analyze results
        issues = analyze_results(df)
        
        # Generate report
        report_file = generate_html_report(issues)
        print(f"Report generated: {report_file}")
        
        # Print summary
        print(f"\nSummary: {len(issues)} issues found")
        if issues:
            print("Please review the report and update profiles to:")
            print("- Use DBA_PROFILE")
            print("- Set password expiry to 170 days")
            print("- Assign complex password verification function")
            
    finally:
        connection.close()

if __name__ == "__main__":
    main()