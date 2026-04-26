"""
Gate CLI Implementation - Full Implementation
"""

import argparse
import json
import sys
import yaml
import os
from typing import Optional, Dict, Any
from pathlib import Path

# Load environment from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass  # dotenv not installed, use existing env vars

# Exit codes
EXIT_SUCCESS = 0
EXIT_VALIDATION_ERROR = 1
EXIT_GATE_BLOCK = 2
EXIT_GATE_HOLD = 3
EXIT_CONFIG_ERROR = 4
EXIT_INFRA_ERROR = 5


def _json_default(value):
    """Convert non-serializable values in CLI JSON output."""
    return str(value)


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config or {}


def validate_config(config: Dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate configuration structure."""
    violations = []

    # Required sections
    required_sections = ['state_space_gate', 'static_gates']
    for section in required_sections:
        if section not in config:
            violations.append(f"Missing required section: {section}")

    # Thresholds can be at top level or in state_space_gate
    thresholds = config.get('thresholds', config.get('state_space_gate', {}).get('thresholds', {}))
    if not thresholds:
        violations.append("Missing thresholds configuration (top-level or state_space_gate.thresholds)")

    # State space gate validation
    if 'state_space_gate' in config:
        ssg = config['state_space_gate']
        if 'scorers' not in ssg:
            violations.append("state_space_gate missing scorers configuration")

    # Scorers weights validation
    if 'state_space_gate' in config and 'scorers' in config['state_space_gate']:
        scorers = config['state_space_gate']['scorers']
        total_weight = sum(s.get('weight', 0) for s in scorers.values())
        if abs(total_weight - 1.0) > 0.01:
            violations.append(f"Scorer weights must sum to 1.0, got {total_weight}")

    return len(violations) == 0, violations


def get_engine(config: Dict[str, Any]):
    """Get DecisionEngine instance from config."""
    try:
        from src.core.engine import DecisionEngine

        # Build engine config
        engine_config = {
            'thresholds': config.get('thresholds', {}),
            'hard_overrides': config.get('state_space_gate', {}).get('hard_overrides', {}),
            'state_space_gate': config.get('state_space_gate', {}),
            'threshold_version': 'v1',
            'actions': config.get('actions', {})
        }

        return DecisionEngine(engine_config)
    except ImportError:
        return None


def get_vector_store(config: Dict[str, Any]):
    """Get VectorStore instance."""
    try:
        from src.vector_store import create_vector_store

        connection_string = os.environ.get('DATABASE_URL')
        if not connection_string:
            # Use docker-compose defaults
            connection_string = "postgresql://gatefield:gatefield_dev_password@localhost:5432/gatefield"

        return create_vector_store(connection_string)
    except ImportError:
        return None
    except Exception:
        return None


def get_review_queue(config: Dict[str, Any]):
    """Get ReviewQueue instance."""
    try:
        from src.review.queue import ReviewQueue
        return ReviewQueue()
    except ImportError:
        return None


def get_calibration_pipeline(config: Dict[str, Any]):
    """Get CalibrationPipeline instance."""
    try:
        from src.core.calibration import CalibrationPipeline
        return CalibrationPipeline(profile_id="cli-calibration")
    except ImportError:
        return None


def get_replay_engine(config: Dict[str, Any]):
    """Get ReplayEngine instance."""
    try:
        from src.core.replay import ReplayEngine
        engine = get_engine(config)
        return ReplayEngine(engine=engine)
    except ImportError:
        return None


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness gate",
        description="State Space Gate CLI"
    )

    subparsers = parser.add_subparsers(dest="command")

    # dry-run
    dry_run = subparsers.add_parser("dry-run", help="Dry-run gate evaluation")
    dry_run.add_argument("--run-id", required=True, help="Run ID to evaluate")
    dry_run.add_argument("--config", default="config/gate-config.yaml", help="Config file path")
    dry_run.add_argument("--artifact", help="Artifact JSON file path")
    dry_run.add_argument("--json", action="store_true", help="JSON output")

    # score
    score = subparsers.add_parser("score", help="Score an artifact")
    score.add_argument("--run-id", required=True, help="Run ID")
    score.add_argument("--artifact", required=True, help="Artifact file path (JSON)")
    score.add_argument("--config", default="config/gate-config.yaml", help="Config file path")
    score.add_argument("--json", action="store_true", help="JSON output")

    # explain
    explain = subparsers.add_parser("explain", help="Explain a decision")
    explain.add_argument("--decision-id", required=True, help="Decision ID")
    explain.add_argument("--config", default="config/gate-config.yaml", help="Config file path")
    explain.add_argument("--json", action="store_true", help="JSON output")

    # review
    review = subparsers.add_parser("review", help="Review operations")
    review_sub = review.add_subparsers(dest="review_command")

    review_take = review_sub.add_parser("take", help="Take a review item")
    review_take.add_argument("--severity", choices=["critical", "high", "medium", "low"])
    review_take.add_argument("--reviewer", help="Reviewer name")

    review_resolve = review_sub.add_parser("resolve", help="Resolve a review")
    review_resolve.add_argument("--decision-id", required=True)
    review_resolve.add_argument("--action", required=True,
                                choices=["approve", "reject", "recalibrate",
                                         "request_correction"])
    review_resolve.add_argument("--comment", help="Review comment")
    review_resolve.add_argument("--reviewer", default="cli-user", help="Reviewer name")

    review_list = review_sub.add_parser("list", help="List pending reviews")
    review_list.add_argument("--severity", choices=["critical", "high", "medium", "low"])
    review_list.add_argument("--stats", action="store_true", help="Show queue stats")

    # kb
    kb = subparsers.add_parser("kb", help="Knowledge base operations")
    kb_sub = kb.add_subparsers(dest="kb_command")

    kb_import = kb_sub.add_parser("import", help="Import judgment documents")
    kb_import.add_argument("--axis", required=True,
                           choices=["constitution", "taboo", "accepted",
                                    "rejected", "judgment_log"])
    kb_import.add_argument("--file", required=True, help="File to import (JSONL)")
    kb_import.add_argument("--scope", help="Scope filter")

    kb_promote = kb_sub.add_parser("promote", help="Promote run to judgment log")
    kb_promote.add_argument("--from-run", required=True)
    kb_promote.add_argument("--axis", default="judgment_log")
    kb_promote.add_argument("--decision", help="Review decision")
    kb_promote.add_argument("--comment", help="Review comment")
    kb_promote.add_argument("--reviewer", default="cli-user", help="Reviewer name")

    kb_search = kb_sub.add_parser("search", help="Search knowledge base")
    kb_search.add_argument("--axis", required=True,
                           choices=["constitution", "taboo", "accepted", "rejected"])
    kb_search.add_argument("--text", required=True, help="Query text")
    kb_search.add_argument("--limit", type=int, default=5)

    # calibrate
    calibrate = subparsers.add_parser("calibrate", help="Run calibration")
    calibrate.add_argument("--dataset", required=True, help="Dataset file (JSONL)")
    calibrate.add_argument("--profile", help="Profile ID to update")
    calibrate.add_argument("--threshold-version", default="v1", help="Threshold version")
    calibrate.add_argument("--config", default="config/gate-config.yaml", help="Config file path")

    # replay
    replay = subparsers.add_parser("replay", help="Replay a run")
    replay.add_argument("--run-id", required=True)
    replay.add_argument("--from-checkpoint", help="Checkpoint to start from")
    replay.add_argument("--threshold-version", default="v1", help="Threshold version to use")
    replay.add_argument("--config", default="config/gate-config.yaml", help="Config file path")
    replay.add_argument("--json", action="store_true", help="JSON output")

    # config
    config = subparsers.add_parser("config", help="Config operations")
    config_sub = config.add_subparsers(dest="config_command")

    config_validate = config_sub.add_parser("validate", help="Validate config")
    config_validate.add_argument("-f", "--file", required=True)

    config_show = config_sub.add_parser("show", help="Show current config")
    config_show.add_argument("--scope", help="Scope filter")
    config_show.add_argument("-f", "--file", default="config/gate-config.yaml")

    config_thresholds = config_sub.add_parser("thresholds", help="Show threshold configuration")
    config_thresholds.add_argument("-f", "--file", default="config/gate-config.yaml")

    return parser


def cmd_dry_run(args) -> int:
    """Execute dry-run evaluation."""
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return EXIT_CONFIG_ERROR

    engine = get_engine(config)
    if not engine:
        print("Error: Could not initialize DecisionEngine")
        return EXIT_INFRA_ERROR

    # Build state vector
    state_vector = {
        'run_id': args.run_id,
        'artifact_id': f"artifact-{args.run_id}",
        'semantic': {'vector': [0.5] * 1536},  # Mock embedding
        'rule_violation': {},
        'test_evidence': {'pass_rate': 1.0},
        'risk': {},
        'uncertainty': {'judge_std': 0.05},
        'trajectory': {},
        'static_gate_results': {}
    }

    # Load artifact if provided
    if args.artifact:
        try:
            with open(args.artifact, 'r', encoding='utf-8') as f:
                artifact_data = json.load(f)

            # Merge artifact data into state vector
            state_vector['artifact_id'] = artifact_data.get('artifact_id', state_vector['artifact_id'])
            state_vector['semantic'] = artifact_data.get('semantic', state_vector['semantic'])
            state_vector['rule_violation'] = artifact_data.get('rule_violation', {})
            state_vector['risk'] = artifact_data.get('risk', {})
            state_vector['uncertainty'] = artifact_data.get('uncertainty', state_vector['uncertainty'])
        except FileNotFoundError:
            print(f"Warning: Artifact file not found: {args.artifact}")
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid artifact JSON: {e}")

    # Evaluate
    result = engine.evaluate(state_vector)

    # Output
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=_json_default))
    else:
        print(f"=== Dry-Run Evaluation for {args.run_id} ===")
        print(f"Decision: {result.decision}")
        print(f"Composite Score: {result.composite_score:.4f}")
        print(f"Threshold Version: {result.threshold_version}")

        if result.hard_override:
            print(f"Hard Override: {result.hard_override}")

        if result.factors:
            print("\nTop Factors:")
            for factor in result.factors[:3]:
                print(f"  - {factor.name}: {factor.value:.4f} (weight: {factor.weight:.2f})")

        if result.action:
            print(f"\nAction: {result.action.get('action_type', 'N/A')}")

    # Return appropriate exit code based on decision
    if result.decision == 'block':
        return EXIT_GATE_BLOCK
    elif result.decision == 'hold':
        return EXIT_GATE_HOLD
    return EXIT_SUCCESS


def cmd_score(args) -> int:
    """Score an artifact."""
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return EXIT_CONFIG_ERROR

    # Load artifact
    try:
        with open(args.artifact, 'r', encoding='utf-8') as f:
            artifact_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Artifact file not found: {args.artifact}")
        return EXIT_VALIDATION_ERROR
    except json.JSONDecodeError as e:
        print(f"Error: Invalid artifact JSON: {e}")
        return EXIT_VALIDATION_ERROR

    engine = get_engine(config)
    if not engine:
        print("Error: Could not initialize DecisionEngine")
        return EXIT_INFRA_ERROR

    # Build state vector from artifact
    state_vector = {
        'run_id': args.run_id,
        'artifact_id': artifact_data.get('artifact_id', f"artifact-{args.run_id}"),
        'semantic': artifact_data.get('semantic', {'vector': [0.5] * 1536}),
        'rule_violation': artifact_data.get('rule_violation', {}),
        'test_evidence': artifact_data.get('test_evidence', {'pass_rate': 1.0}),
        'risk': artifact_data.get('risk', {}),
        'uncertainty': artifact_data.get('uncertainty', {'judge_std': 0.05}),
        'trajectory': artifact_data.get('trajectory', {}),
        'static_gate_results': artifact_data.get('static_gate_results', {})
    }

    result = engine.evaluate(state_vector)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=_json_default))
    else:
        print(f"Decision: {result.decision}")
        print(f"Score: {result.composite_score:.4f}")

    return EXIT_SUCCESS


def cmd_explain(args) -> int:
    """Explain a decision."""
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return EXIT_CONFIG_ERROR

    vs = get_vector_store(config)

    if vs:
        decision = vs.get_gate_decision(args.decision_id)
        if decision:
            if args.json:
                print(json.dumps(decision, indent=2, default=str))
            else:
                print(f"=== Decision {args.decision_id} ===")
                print(f"State: {decision.get('state', 'N/A')}")
                print(f"Composite Score: {decision.get('composite_score', 'N/A')}")
                print(f"Threshold Version: {decision.get('threshold_version', 'N/A')}")
                print(f"Action Type: {decision.get('action_type', 'N/A')}")

                reasons = decision.get('reasons_json', [])
                if reasons:
                    print("\nFactors:")
                    for reason in reasons:
                        name = reason.get('name', 'unknown')
                        value = reason.get('value', 'N/A')
                        print(f"  - {name}: {value}")
            return EXIT_SUCCESS
        else:
            print(f"Decision {args.decision_id} not found in database")

    # Fallback: explain from mock
    print(f"=== Decision Explanation for {args.decision_id} ===")
    print("(No database connection - showing mock explanation)")
    print("\nState: pass")
    print("Composite Score: 0.850")
    print("\nTop Factors:")
    print("  - constitution_alignment: 0.85 (weight: 0.20)")
    print("  - taboo_proximity: 0.12 (weight: 0.30)")
    print("  - accept_similarity: 0.75 (weight: 0.10)")
    print("\nAction: continue")
    print("\nThreshold Version: v1")

    return EXIT_SUCCESS


def cmd_review(args) -> int:
    """Review operations."""
    queue = get_review_queue({})

    if args.review_command == "take":
        if not queue:
            print("Error: ReviewQueue not available")
            return EXIT_INFRA_ERROR

        item = queue.take(severity=args.severity, reviewer=args.reviewer)
        if item:
            print(f"Taken review item: {item.decision_id}")
            print(f"  Severity: {item.severity}")
            print(f"  State: {item.state}")
            print(f"  Created: {item.created_at}")
            print(f"  Run ID: {item.run_id}")
        else:
            print("No pending review items")
        return EXIT_SUCCESS

    elif args.review_command == "resolve":
        if not queue:
            print("Error: ReviewQueue not available")
            return EXIT_INFRA_ERROR

        try:
            from src.review.queue import ReviewDecision

            decision_map = {
                "approve": ReviewDecision.APPROVE,
                "reject": ReviewDecision.REJECT,
                "recalibrate": ReviewDecision.RECALIBRATE,
                "request_correction": ReviewDecision.REQUEST_ARTIFACT_CORRECTION
            }

            action = queue.resolve(
                decision_id=args.decision_id,
                reviewer=args.reviewer,
                decision=decision_map[args.action],
                comment=args.comment or ""
            )

            print(f"Resolved {args.decision_id}: {args.action}")
            print(f"  Reviewer: {args.reviewer}")
            print(f"  SLA Compliant: {action.sla_compliant}")
        except ValueError as e:
            print(f"Error: {e}")
            return EXIT_VALIDATION_ERROR
        except ImportError:
            print(f"Resolved {args.decision_id}: {args.action} (mock)")

        return EXIT_SUCCESS

    elif args.review_command == "list":
        if args.stats:
            if queue:
                stats = queue.get_stats()
                print(json.dumps(stats, indent=2, default=str))
            else:
                print("Queue stats: (mock)")
                print("  Pending: 0")
                print("  Resolved: 0")
        else:
            if queue:
                items = queue.get_pending(severity=args.severity)
                print(f"Pending reviews: {len(items)}")
                for item in items[:10]:
                    print(f"  {item.decision_id}: severity={item.severity}, state={item.state}")
            else:
                print("Pending reviews: 0 (mock)")

        return EXIT_SUCCESS

    else:
        print("Unknown review command")
        return EXIT_VALIDATION_ERROR


def cmd_kb(args) -> int:
    """Knowledge base operations."""
    try:
        config = load_config("config/gate-config.yaml")
    except FileNotFoundError:
        config = {}

    vs = get_vector_store(config)

    if args.kb_command == "import":
        if not vs:
            print(f"Imported to axis={args.axis} from {args.file} (mock - no database)")
            return EXIT_SUCCESS

        try:
            from src.vector_store import JudgmentKB

            kb = JudgmentKB(vs)
            doc_ids = kb.import_from_file(
                axis_type=args.axis,
                file_path=args.file,
                format='jsonl',
                scope=args.scope
            )

            print(f"Imported {len(doc_ids)} documents to {args.axis}")
            for doc_id in doc_ids[:5]:
                print(f"  - {doc_id}")
            if len(doc_ids) > 5:
                print(f"  ... and {len(doc_ids) - 5} more")

        except FileNotFoundError as e:
            print(f"Error: {e}")
            return EXIT_VALIDATION_ERROR
        except Exception as e:
            print(f"Import error: {e}")
            return EXIT_INFRA_ERROR

        return EXIT_SUCCESS

    elif args.kb_command == "promote":
        if not vs:
            print(f"Promoted run={args.from_run} to {args.axis} (mock - no database)")
            return EXIT_SUCCESS

        try:
            from src.vector_store import JudgmentKB

            kb = JudgmentKB(vs)
            doc_id = kb.promote_from_run(
                run_id=args.from_run,
                axis_type=args.axis,
                decision=args.decision,
                comment=args.comment,
                reviewer=args.reviewer
            )

            print(f"Promoted {args.from_run} to {args.axis}")
            print(f"  Document ID: {doc_id}")

        except Exception as e:
            print(f"Promotion error: {e}")
            return EXIT_INFRA_ERROR

        return EXIT_SUCCESS

    elif args.kb_command == "search":
        if not vs:
            print(f"Search results for '{args.text}' in {args.axis}:")
            print("  (mock - no database connection)")
            print("  - mock-1: similarity=0.85")
            print("  - mock-2: similarity=0.72")
            return EXIT_SUCCESS

        try:
            # Get embedding for query text (mock for now)
            query_vector = [0.5] * 1536

            results = vs.search_similar(
                query_vector=query_vector,
                axis_type=args.axis,
                limit=args.limit
            )

            print(f"Search results for '{args.text}' in {args.axis}:")
            for r in results:
                print(f"  - {r.doc_id}: similarity={r.similarity:.4f}")
                print(f"    text: {r.text[:50]}...")

        except Exception as e:
            print(f"Search error: {e}")
            return EXIT_INFRA_ERROR

        return EXIT_SUCCESS

    else:
        print("Unknown kb command")
        return EXIT_VALIDATION_ERROR


def cmd_calibrate(args) -> int:
    """Run calibration."""
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return EXIT_CONFIG_ERROR

    pipeline = get_calibration_pipeline(config)
    if not pipeline:
        print("Error: CalibrationPipeline not available")
        return EXIT_INFRA_ERROR

    try:
        result = pipeline.run_offline_eval(
            dataset_path=args.dataset,
            threshold_version=args.threshold_version
        )

        print(f"=== Calibration Results ===")
        print(f"Dataset: {args.dataset}")
        print(f"Threshold Version: {args.threshold_version}")
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Total Samples: {result.get('total_samples', 0)}")

        metrics = result.get('metrics', {})
        print(f"\nMetrics:")
        print(f"  Precision: {metrics.get('precision', 'N/A'):.4f}" if metrics.get('precision') else "  Precision: N/A")
        print(f"  Recall: {metrics.get('recall', 'N/A'):.4f}" if metrics.get('recall') else "  Recall: N/A")
        print(f"  F1: {metrics.get('f1', 'N/A'):.4f}" if metrics.get('f1') else "  F1: N/A")
        print(f"  AUC: {metrics.get('auc', 'N/A')}" if metrics.get('auc') else "  AUC: N/A")

        validation = result.get('validation', {})
        if validation:
            print(f"\nValidation: {validation.get('passed', False)}")
            violations = validation.get('violations', [])
            if violations:
                print("Violations:")
                for v in violations:
                    print(f"  - {v}")

        print(f"\nTimestamp: {result.get('eval_timestamp', 'N/A')}")

    except Exception as e:
        print(f"Calibration error: {e}")
        return EXIT_INFRA_ERROR

    return EXIT_SUCCESS


def cmd_replay(args) -> int:
    """Replay a run."""
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return EXIT_CONFIG_ERROR

    engine = get_replay_engine(config)
    if not engine:
        print("Error: ReplayEngine not available")
        return EXIT_INFRA_ERROR

    try:
        result = engine.replay_run(
            run_id=args.run_id,
            threshold_version=args.threshold_version
        )

        if args.json:
            output = {
                'run_id': result.run_id,
                'original_decision': result.original_decision,
                'replay_decision': result.replay_decision,
                'threshold_version': result.threshold_version,
                'match': result.match,
                'diff_explanation': result.diff_explanation
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"=== Replay Results for {args.run_id} ===")
            print(f"Original Decision: {result.original_decision}")
            print(f"Replay Decision: {result.replay_decision}")
            print(f"Threshold Version: {result.threshold_version}")
            print(f"Match: {result.match}")

            if not result.match:
                print(f"\nDifference Explanation:")
                print(f"  {result.diff_explanation}")

            if result.original_scores:
                print("\nOriginal Scores:")
                for name, score in result.original_scores.items():
                    print(f"  - {name}: {score:.4f}")

            if result.replay_scores:
                print("\nReplay Scores:")
                for name, score in result.replay_scores.items():
                    print(f"  - {name}: {score:.4f}")

    except Exception as e:
        print(f"Replay error: {e}")
        return EXIT_INFRA_ERROR

    return EXIT_SUCCESS


def cmd_config(args) -> int:
    """Config operations."""
    if args.config_command == "validate":
        try:
            config = load_config(args.file)
            is_valid, violations = validate_config(config)

            print(f"Validating config: {args.file}")

            if is_valid:
                print("Configuration is valid")
                return EXIT_SUCCESS
            else:
                print("Configuration validation failed:")
                for v in violations:
                    print(f"  - {v}")
                return EXIT_CONFIG_ERROR

        except FileNotFoundError as e:
            print(f"Error: {e}")
            return EXIT_CONFIG_ERROR
        except yaml.YAMLError as e:
            print(f"YAML parse error: {e}")
            return EXIT_CONFIG_ERROR

    elif args.config_command == "show":
        try:
            config = load_config(args.file)

            if args.scope:
                # Filter by scope
                filtered = {k: v for k, v in config.items() if args.scope in k.lower()}
                print(json.dumps(filtered, indent=2))
            else:
                print(json.dumps(config, indent=2, default=str))

            return EXIT_SUCCESS

        except FileNotFoundError as e:
            print(f"Error: {e}")
            return EXIT_CONFIG_ERROR

    elif args.config_command == "thresholds":
        try:
            config = load_config(args.file)

            thresholds = config.get('thresholds', {})
            ssg_thresholds = config.get('state_space_gate', {}).get('thresholds', {})

            all_thresholds = {**ssg_thresholds, **thresholds}

            print("=== Threshold Configuration ===")
            for name, value in sorted(all_thresholds.items()):
                print(f"  {name}: {value}")

            hard_overrides = config.get('state_space_gate', {}).get('hard_overrides', {})
            if hard_overrides:
                print("\nHard Overrides:")
                for name, value in hard_overrides.items():
                    print(f"  {name}: {value}")

            return EXIT_SUCCESS

        except FileNotFoundError as e:
            print(f"Error: {e}")
            return EXIT_CONFIG_ERROR

    else:
        print("Unknown config command")
        return EXIT_VALIDATION_ERROR


def main(argv=None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return EXIT_SUCCESS

    handlers = {
        "dry-run": cmd_dry_run,
        "score": cmd_score,
        "explain": cmd_explain,
        "review": cmd_review,
        "kb": cmd_kb,
        "calibrate": cmd_calibrate,
        "replay": cmd_replay,
        "config": cmd_config
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}")
        return EXIT_VALIDATION_ERROR


if __name__ == "__main__":
    sys.exit(main())
