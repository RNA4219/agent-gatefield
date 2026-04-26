#!/usr/bin/env python3
"""
Gate Health Monitor - Production monitoring for agent-gatefield

Checks operational KPIs and alerts on threshold violations.
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / '.env')
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# KPI thresholds from requirements
KPI_THRESHOLDS = {
    'review_load_reduction_min': 0.30,
    'critical_miss_rate_max': 0.0,
    'high_miss_rate_max': 0.05,
    'false_escalation_rate_max': 0.15,
    'replay_reproducibility_min': 0.99,
    'state_vector_coverage_min': 0.95,
    'audit_completeness_min': 1.0,
}

# Alert thresholds from RUNBOOK 4.2
ALERT_THRESHOLDS = {
    'coverage_drop_pct': 90,  # High
    'queue_backlog_critical': 5,  # Critical (> 5 pending for > 15 min)
    'queue_backlog_age_minutes': 15,
    'high_miss_rate_pct': 5,  # High
    'false_escalation_pct': 20,  # Medium (> 20% for 1 hour)
    'embedding_worker_down_minutes': 5,  # High
    'db_connection_pct': 80,  # Medium
}

ALERT_LEVELS = {
    'info': 0,
    'warning': 1,
    'critical': 2,
    'block': 3,
}


def get_db_connection():
    """Get database connection."""
    try:
        import psycopg2
        conn_str = os.environ.get('DATABASE_URL')
        if not conn_str:
            conn_str = "postgresql://gatefield:gatefield_prod_password@localhost:5432/gatefield"

        # Parse connection string to avoid Windows encoding issues
        conn = psycopg2.connect(
            host='localhost',
            user='gatefield',
            password='gatefield_prod_password',
            database='gatefield',
            port=5432
        )
        conn.set_client_encoding('UTF8')
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None


def check_state_vector_coverage(conn, hours=24):
    """Check state vector coverage (95%+ target)."""
    if not conn:
        return None, "Database unavailable"

    try:
        with conn.cursor() as cur:
            interval_str = f"{hours} hours"
            # Total runs in period
            cur.execute(f"""
                SELECT COUNT(*) FROM gate_decisions
                WHERE created_at > NOW() - INTERVAL '{interval_str}'
            """)
            decisions = cur.fetchone()[0]

            # State vectors with embedding
            cur.execute(f"""
                SELECT COUNT(*) FROM state_vectors
                WHERE created_at > NOW() - INTERVAL '{interval_str}'
                AND semantic_embedding IS NOT NULL
            """)
            vectors = cur.fetchone()[0]

            if decisions == 0:
                return None, "No decisions in period"

            coverage = vectors / decisions
            status = 'ok' if coverage >= KPI_THRESHOLDS['state_vector_coverage_min'] else 'warning'
            return coverage, status
    except Exception as e:
        return None, str(e)


def check_decision_distribution(conn, hours=24):
    """Check decision distribution."""
    if not conn:
        return None, "Database unavailable"

    try:
        interval_str = f"{hours} hours"
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT state, COUNT(*)
                FROM gate_decisions
                WHERE created_at > NOW() - INTERVAL '{interval_str}'
                GROUP BY state
            """)
            results = dict(cur.fetchall())
            return results, 'ok'
    except Exception as e:
        return None, str(e)


def check_review_queue(conn):
    """Check review queue backlog and SLA breaches."""
    if not conn:
        return None, "Database unavailable"

    try:
        with conn.cursor() as cur:
            # Pending reviews count (reviews without previous_decision meaning pending)
            cur.execute("""
                SELECT COUNT(*) FROM human_reviews
                WHERE previous_decision IS NULL OR previous_decision = ''
            """)
            pending_count = cur.fetchone()[0]

            # Total reviews in last 24 hours
            cur.execute("""
                SELECT COUNT(*) FROM human_reviews
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            total_24h = cur.fetchone()[0]

            status = 'ok'
            return {'pending': pending_count, 'reviews_24h': total_24h}, status
    except Exception as e:
        return None, str(e)


def check_audit_completeness(conn, hours=24):
    """Check audit completeness (100% target)."""
    if not conn:
        return None, "Database unavailable"

    try:
        interval_str = f"{hours} hours"
        with conn.cursor() as cur:
            # Decisions without trace_id
            cur.execute(f"""
                SELECT COUNT(*) FROM gate_decisions
                WHERE created_at > NOW() - INTERVAL '{interval_str}'
                AND (run_id IS NULL OR threshold_version IS NULL)
            """)
            incomplete = cur.fetchone()[0]

            cur.execute(f"""
                SELECT COUNT(*) FROM gate_decisions
                WHERE created_at > NOW() - INTERVAL '{interval_str}'
            """)
            total = cur.fetchone()[0]

            if total == 0:
                return None, "No decisions in period"

            completeness = (total - incomplete) / total
            status = 'critical' if completeness < KPI_THRESHOLDS['audit_completeness_min'] else 'ok'
            return completeness, status
    except Exception as e:
        return None, str(e)


def check_top_block_reasons(conn, hours=24, limit=5):
    """Check top blocking reasons."""
    if not conn:
        return None, "Database unavailable"

    try:
        interval_str = f"{hours} hours"
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT reasons_json->>'top_factor', COUNT(*)
                FROM gate_decisions
                WHERE state = 'block'
                AND created_at > NOW() - INTERVAL '{interval_str}'
                GROUP BY reasons_json->>'top_factor'
                ORDER BY COUNT(*) DESC
                LIMIT {limit}
            """)
            reasons = cur.fetchall()
            return reasons, 'ok'
    except Exception as e:
        return None, str(e)


def check_coverage_drop(conn, hours=24):
    """Check for coverage drop alert (< 90%)."""
    if not conn:
        return None, "Database unavailable"

    try:
        interval_str = f"{hours} hours"
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT COUNT(DISTINCT sv.run_id) as with_vectors,
                       COUNT(DISTINCT gd.run_id) as total_runs
                FROM gate_decisions gd
                LEFT JOIN state_vectors sv ON gd.run_id = sv.run_id
                WHERE gd.created_at > NOW() - INTERVAL '{interval_str}'
            """)
            row = cur.fetchone()
            with_vectors = row[0] or 0
            total_runs = row[1] or 0

            if total_runs == 0:
                return None, "No decisions in period"

            coverage = with_vectors / total_runs * 100
            status = 'critical' if coverage < ALERT_THRESHOLDS['coverage_drop_pct'] else 'ok'
            return {'coverage_pct': round(coverage, 2), 'with_vectors': with_vectors, 'total_runs': total_runs}, status
    except Exception as e:
        return None, str(e)


def check_queue_backlog(conn):
    """Check for queue backlog alert (critical > 5 for > 15 min)."""
    if not conn:
        return None, "Database unavailable"

    try:
        with conn.cursor() as cur:
            # Pending reviews older than 15 minutes
            cur.execute("""
                SELECT COUNT(*) FROM human_reviews
                WHERE (previous_decision IS NULL OR previous_decision = '')
                AND created_at < NOW() - INTERVAL '15 minutes'
            """)
            critical_pending = cur.fetchone()[0]

            # Total pending
            cur.execute("""
                SELECT COUNT(*) FROM human_reviews
                WHERE previous_decision IS NULL OR previous_decision = ''
            """)
            total_pending = cur.fetchone()[0]

            status = 'critical' if critical_pending >= ALERT_THRESHOLDS['queue_backlog_critical'] else 'ok'
            return {'critical_pending': critical_pending, 'total_pending': total_pending}, status
    except Exception as e:
        return None, str(e)


def check_embedding_worker(conn):
    """Check for embedding worker down alert (> 5 min without new embedding)."""
    if not conn:
        return None, "Database unavailable"

    try:
        with conn.cursor() as cur:
            # Last embedding timestamp
            cur.execute("""
                SELECT MAX(created_at) FROM judgment_embeddings
            """)
            last_embedding = cur.fetchone()[0]

            if last_embedding is None:
                return {'last_embedding': None, 'status': 'no_embeddings'}, 'warning'

            # Check if older than threshold using interval comparison
            cur.execute("""
                SELECT COUNT(*) FROM judgment_embeddings
                WHERE created_at > NOW() - INTERVAL '5 minutes'
            """)
            recent_count = cur.fetchone()[0]

            status = 'critical' if recent_count == 0 else 'ok'
            return {'last_embedding': str(last_embedding), 'recent_5min': recent_count}, status
    except Exception as e:
        return None, str(e)


def check_threshold_version_consistency(conn):
    """Check that all decisions use consistent threshold version."""
    if not conn:
        return None, "Database unavailable"

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT threshold_version, COUNT(*)
                FROM gate_decisions
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY threshold_version
            """)
            versions = cur.fetchall()

            if len(versions) == 0:
                return {'versions': [], 'status': 'no_decisions'}, 'ok'

            # Check if multiple versions in use
            if len(versions) > 1:
                return {'versions': dict(versions), 'status': 'multiple_versions'}, 'warning'

            return {'versions': dict(versions), 'status': 'consistent'}, 'ok'
    except Exception as e:
        return None, str(e)


def run_health_check(output_format='text'):
    """Run all health checks and generate report."""
    conn = get_db_connection()
    if not conn:
        logger.error("Cannot connect to database")
        return False

    results = {
        'timestamp': datetime.now().isoformat(),
        'checks': {},
        'alerts': [],
        'status': 'ok',
    }

    # Run checks
    checks = [
        ('state_vector_coverage', check_state_vector_coverage),
        ('decision_distribution', check_decision_distribution),
        ('review_queue', check_review_queue),
        ('audit_completeness', check_audit_completeness),
        ('top_block_reasons', check_top_block_reasons),
        ('coverage_drop', check_coverage_drop),
        ('queue_backlog', check_queue_backlog),
        ('embedding_worker', check_embedding_worker),
        ('threshold_version', check_threshold_version_consistency),
    ]

    for name, check_func in checks:
        value, status = check_func(conn)
        results['checks'][name] = {
            'value': value,
            'status': status,
        }
        if status in ('warning', 'critical', 'block'):
            results['alerts'].append({
                'check': name,
                'level': status,
                'value': value,
            })
            if ALERT_LEVELS.get(status, 0) > ALERT_LEVELS.get(results['status'], 0):
                results['status'] = status

    conn.close()

    # Output
    if output_format == 'json':
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"=== Gate Health Check ===")
        print(f"Timestamp: {results['timestamp']}")
        print(f"Overall Status: {results['status']}")
        print()
        for name, data in results['checks'].items():
            value = data['value']
            status = data['status']
            if isinstance(value, dict):
                value_str = json.dumps(value, default=str)
            elif isinstance(value, (list, tuple)):
                value_str = str(value)
            else:
                value_str = str(value) if value else 'N/A'
            print(f"  {name}: {value_str} [{status}]")

        if results['alerts']:
            print()
            print(f"=== Alerts ({len(results['alerts'])}) ===")
            for alert in results['alerts']:
                print(f"  [{alert['level']}] {alert['check']}: {alert['value']}")

    return results['status'] in ('ok', 'warning')


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Gate health monitor')
    parser.add_argument('--json', action='store_true', help='JSON output')
    parser.add_argument('--hours', type=int, default=24, help='Check period in hours')
    args = parser.parse_args()

    success = run_health_check(output_format='json' if args.json else 'text')
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()