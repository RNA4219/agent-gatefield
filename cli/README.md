# CLI Design

## Commands

### Gate Operations

```bash
# Dry-run gate evaluation
harness gate dry-run --run-id RUN123

# Score an artifact
harness gate score --run-id RUN123 --artifact ./patch.diff

# Explain a decision
harness gate explain --decision-id DEC456
```

### Review Operations

```bash
# Take a review item
harness gate review take --severity critical

# Resolve a review
harness gate review resolve --decision-id DEC456 --action approve --comment "境界内"
```

### Knowledge Base Operations

```bash
# Import judgment documents
harness gate kb import --axis taboo --file taboo_cases.yaml

# Promote a run to judgment logs
harness gate kb promote --from-run RUN123 --axis judgment_logs
```

### Calibration Operations

```bash
# Run calibration on a dataset
harness gate calibrate --dataset datasets/gates_v1.jsonl

# Replay a run with specific threshold version
harness gate replay --run-id RUN123 --from-checkpoint CP789
```

### Config Operations

```bash
# Validate configuration
harness gate config validate -f gate-config.yaml

# Show current thresholds
harness gate config show --scope service-a
```

## Output Formats

- Default: human-readable table
- `--json`: JSON output for scripting
- `--verbose`: detailed explanation with top factors and exemplars

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation error |
| 2 | Gate block |
| 3 | Gate hold (requires review) |
| 4 | Configuration error |
| 5 | Network/infrastructure error |