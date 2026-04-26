# Performance Specification

## Document Information

| Field | Value |
|---|---|
| Document ID | AGF-SPEC-PERF-001 |
| Version | 1.0.0 |
| Status | Production Requirements Frozen |
| Last Updated | 2026-04-26 |
| Source Reference | requirements.md (AGF-REQ series) |

---

## 1. Latency Requirements

### 1.1 Decision Latency

Gate decision latency is measured from artifact emission to final gate decision (pass/warn/hold/block).

| Component | Target Latency | P90 Target | P99 Target | SLA Requirement |
|---|---|---|---|---|
| Static gate execution | < 30s | 60s | 120s | Deterministic block within 30s |
| State vector generation | < 5s | 10s | 30s | 95% coverage target |
| Embedding generation (single artifact) | < 2s | 5s | 15s | API timeout 30s max |
| Vector search (top-k retrieval) | < 100ms | 500ms | 2s | HNSW index requirement |
| Scorer computation | < 500ms | 2s | 5s | All scorers parallel |
| Composite decision | < 200ms | 500ms | 1s | Weighted aggregation |
| Total gate decision | < 60s | 120s | 300s | High class SLA |

### 1.2 Human Review SLA

| Severity Class | ACK Deadline | Decision Deadline | Timeout Action |
|---|---|---|---|
| Critical | 15 minutes | 60 minutes | Fail closed + escalation |
| High | 60 minutes | 240 minutes | Fail closed + escalation |
| Medium | Same business day | Next business day | Backlog escalation |
| Low | No requirement | Backlog | Manual review |

### 1.3 Dashboard Freshness

| Metric | Target | Alert Threshold |
|---|---|---|
| Trace ingest to visualization | < 60 seconds | > 90 seconds |
| Review writeback propagation | < 5 seconds | > 10 seconds |
| KPI dashboard update | < 5 minutes | > 15 minutes |
| Alert notification delivery | < 30 seconds | > 60 seconds |

### 1.4 Embedding Generation Latency

| Operation | Batch Size | Expected Latency | Timeout |
|---|---|---|---|
| Single embedding (local-hash-embedding-v1) | 1 | < 50ms | 5s |
| Batch embedding (10 items) | 10 | < 250ms | 10s |
| Batch embedding (100 items) | 100 | < 2s | 30s |
| Batch embedding (1000 items) | 1000 | < 20s | 120s |
| Re-embed job (full KB) | varies | hours | N/A (background) |

---

## 2. Throughput Requirements

### 2.1 Run Processing Capacity

| Metric | MVP Target | Production Target | Scaling Trigger |
|---|---|---|---|
| Max runs per minute | 10 runs | 100 runs | > 80% sustained |
| Max artifacts per run | 5 artifacts | 20 artifacts | Average > 10 |
| Concurrent state vector generation | 5 parallel | 50 parallel | Queue depth > 20 |
| Concurrent vector searches | 20 QPS | 200 QPS | P99 > 2s |

### 2.2 Review Queue Capacity

| Metric | MVP Target | Production Target | Notes |
|---|---|---|---|
| Concurrent pending reviews | 20 items | 200 items | Queue depth alert |
| Review resolution rate | 5/hour | 50/hour | Team scaling metric |
| Queue drain time (Critical) | < 4 hours | < 1 hour | SLA compliance |
| Queue drain time (High) | < 8 hours | < 4 hours | SLA compliance |

### 2.3 Batch Embedding Capacity

| Operation | Throughput | Notes |
|---|---|---|
| Initial KB ingestion | 1000 items/hour | Background job |
| Daily embedding updates | 500 items/hour | Incremental |
| Full KB re-embed | 10k items/day | Scheduled maintenance |
| Real-time artifact embedding | 100 items/minute | Per-run processing |

### 2.4 API Rate Limits

| Endpoint | Rate Limit | Burst Limit | Notes |
|---|---|---|---|
| Gate decision API | 100 req/min | 20 req/sec | Per-client |
| Review queue API | 50 req/min | 10 req/sec | Per-reviewer |
| Dashboard query API | 200 req/min | 50 req/sec | Read-only |
| Embedding worker API | 500 req/min | 100 req/sec | Internal |
| Audit export API | 10 req/min | 2 req/sec | Bulk operations |

---

## 3. Resource Limits

### 3.1 Memory Requirements

| Component | MVP Minimum | Production Minimum | Peak Estimate |
|---|---|---|---|
| State encoder service | 512 MB | 2 GB | 4 GB (large artifacts) |
| Embedding worker | 256 MB | 1 GB | 2 GB (batch processing) |
| Vector search service | 512 MB | 4 GB | 8 GB (HNSW index) |
| Dashboard frontend | 256 MB | 512 MB | 1 GB (complex queries) |
| Postgres/pgvector | 2 GB | 16 GB | 32 GB (10M+ vectors) |
| Total system | 4 GB | 32 GB | 64 GB |

### 3.2 CPU Requirements

| Component | MVP | Production | Notes |
|---|---|---|---|
| State encoder | 1 vCPU | 4 vCPU | Parallel scorer execution |
| Embedding worker | 1 vCPU | 2 vCPU | Network-bound primarily |
| Vector search | 2 vCPU | 8 vCPU | ANN index operations |
| Composite decision | 1 vCPU | 2 vCPU | Low compute requirement |
| Postgres/pgvector | 2 vCPU | 8 vCPU | Query + index maintenance |

### 3.3 Storage Requirements (Embeddings)

| Scale | 1536d Raw Size | 3072d Raw Size | Index Overhead | Total Estimate |
|---|---|---|---|---|
| 100k items | 0.67 GB | 1.24 GB | +30% | 1536d: ~1 GB |
| 1M items | 6.68 GB | 12.40 GB | +30% | 1536d: ~9 GB |
| 10M items | 66.76 GB | 123.98 GB | +30% | 1536d: ~87 GB |

**Calculation basis:**
- Dense vector = float32 (4 bytes per dimension)
- Metadata overhead = 1 KB per item (average)
- Index overhead (HNSW) = ~30% additional storage

### 3.4 Database Size Estimates

| Table | MVP Estimate | 1M Items | 10M Items | Growth Rate |
|---|---|---|---|---|
| `judgment_documents` | 50 MB | 500 MB | 5 GB | Text + metadata |
| `judgment_embeddings` | 0.7 GB | 7 GB | 70 GB | Vector storage |
| `state_vectors` | 100 MB | 1 GB | 10 GB | Per-run records |
| `gate_decisions` | 50 MB | 500 MB | 5 GB | Decision packets |
| `human_reviews` | 10 MB | 100 MB | 1 GB | Review records |
| `audit_events` | 200 MB | 2 GB | 20 GB | OTel traces |
| **Total** | ~1.1 GB | ~11 GB | ~111 GB | Annual ~50% growth |

### 3.5 Retention Storage Impact

| Data Class | Retention | Annual Growth | Purge Impact |
|---|---|---|---|
| Audit/decision logs | 365 days | ~5 GB/year | 5% monthly reduction |
| Trace metadata | 180 days | ~2 GB/year | 10% monthly reduction |
| Redacted artifacts | 90 days | ~1 GB/year | 25% monthly reduction |
| Human corrections | 365 days | ~100 MB/year | Minimal |
| Intermediate vectors | 30 days | ~500 MB/year | Significant monthly purge |

---

## 4. Cost Estimates

### 4.1 Embedding API Costs

Based on OpenAI pricing (text-embedding-3-large: $0.13/1M tokens, text-embedding-3-small: $0.02/1M tokens).

| Volume | text-embedding-3-large | text-embedding-3-small | Monthly Recurring |
|---|---|---|---|
| 100k tokens | $0.013 | $0.002 | N/A (one-time) |
| 1M tokens | $0.13 | $0.02 | ~$0.50/month (daily updates) |
| 10M tokens | $1.30 | $0.20 | ~$5/month |
| 100M tokens | $13.00 | $2.00 | ~$50/month |
| 1B tokens | $130.00 | $20.00 | ~$500/month (at capacity) |

### 4.2 Vector Storage Costs (OpenAI Hosted)

Based on OpenAI hosted vector store pricing: 1GB free, then $0.10/GB/day.

| Scale | 1536d Monthly | 3072d Monthly | Free Tier Usage |
|---|---|---|---|
| 100k items | ~$17/month | ~$34/month | 1536d: 1GB free covers most |
| 1M items | ~$17/month | ~$34/month | 3072d exceeds free tier |
| 10M items | ~$197/month | ~$369/month | Both exceed free tier |

**Note:** MVP uses self-hosted pgvector, not OpenAI hosted storage.

### 4.3 Self-Hosted Postgres/pgvector Costs

| Configuration | Monthly Estimate | Annual Estimate | Notes |
|---|---|---|---|
| MVP (4GB RAM, 2 vCPU) | $50-100 | $600-1200 | Cloud instance pricing |
| Production (16GB RAM, 8 vCPU) | $200-400 | $2400-4800 | Depends on provider |
| Storage (100GB SSD) | $10-20 | $120-240 | Block storage pricing |
| Backup storage (50GB) | $5-10 | $60-120 | 7-day retention |

### 4.4 Compute Costs

| Component | MVP Monthly | Production Monthly | Notes |
|---|---|---|---|
| State encoder service | $20-50 | $100-200 | Container orchestration |
| Embedding worker | $10-30 | $50-100 | Scaling with throughput |
| Dashboard frontend | $10-30 | $50-100 | Web hosting |
| Total compute | $40-110 | $200-400 | Before DB costs |

### 4.5 Total Monthly Budget Summary

| Category | MVP Budget | Production Budget | Monthly Cap |
|---|---|---|---|
| Embedding API | $50 | $200 | 40% of total |
| Vector DB/Storage | $100 | $400 | 40% of total |
| Compute | $50 | $200 | 20% of total |
| **Total** | **$200** | **$800** | **$500 MVP cap** |

**Budget Alert Thresholds:**
- 80% ($400): Warn alert triggered
- 100% ($500): Hold alert triggered, operations paused

---

## 5. Scaling Strategy

### 5.1 pgvector to Milvus Migration Thresholds

| Metric | pgvector Limit | Migration Trigger | Milvus Threshold |
|---|---|---|---|
| Vector count | ~10M | > 8M sustained | 100M+ |
| Query QPS | ~100 | P99 > 2s at 80 QPS | 1000+ QPS |
| Index build time | hours | > 4 hours for re-index | Minutes |
| Memory usage | 32 GB | > 80% sustained | Distributed |

### 5.2 Horizontal Scaling Triggers

| Component | Scale Trigger | Scaling Action | Auto-scale Policy |
|---|---|---|---|
| State encoder | Queue depth > 20 | Add workers | CPU > 80% for 5 min |
| Embedding worker | API queue > 50 | Parallel workers | Memory > 70% |
| Vector search | P99 latency > 2s | Index replicas | Query queue depth |
| Dashboard | Request latency > 1s | Frontend replicas | Connection count |

### 5.3 Index Performance Characteristics

| Index Type | Build Time | Query Latency | Memory Usage | Recall | Recommended Use |
|---|---|---|---|---|---|
| Exact (brute force) | None | O(n) | Minimal | 100% | < 100k vectors |
| IVFFlat | Minutes | Low | Moderate | 90-95% | 100k-1M vectors |
| HNSW | Hours | Very low | High | 95-99% | 1M-10M vectors |
| HNSW + PQ | Hours | Low | Moderate | 90-95% | 10M+ vectors |

**MVP Recommendation:** HNSW with m=16, ef_construction=64 for balance of recall and build time.

### 5.4 Index Tuning Parameters

| Parameter | HNSW Default | MVP Setting | Production Setting | Impact |
|---|---|---|---|---|
| `m` (connections) | 16 | 16 | 32 | Higher = more memory, better recall |
| `ef_construction` | 64 | 64 | 128 | Higher = longer build, better recall |
| `ef_search` | 64 | 40 | 100 | Higher = slower query, better recall |
| `lists` (IVFFlat) | 100 | N/A | sqrt(n) | For IVFFlat only |

### 5.5 Distance Metrics Performance

| Metric | CPU Cost | Recall Quality | Recommended Use |
|---|---|---|---|
| L2 (Euclidean) | Low | Good for normalized vectors | Default |
| Cosine | Medium | Best for semantic similarity | MVP default |
| Inner Product | Low | Good for normalized vectors | Alternative |
| L1 (Manhattan) | Medium | Alternative clustering | Not recommended |
| Hamming/Jaccard | Low | Binary/sparse vectors | Not for embeddings |

---

## 6. Performance Testing

### 6.1 Benchmark Procedures

| Test | Procedure | Target Metric | Pass Criteria |
|---|---|---|---|
| Embedding latency | 1000 single embeddings | P99 < 5s | 95% < 2s |
| Vector search | 10k queries at varying k | P99 < 500ms | P90 < 100ms |
| Gate decision | 100 end-to-end runs | P99 < 300s | P90 < 120s |
| Concurrent load | 50 parallel runs | No queue overflow | Graceful degradation |
| Index build | Full KB re-index | < 4 hours | < 2 hours optimal |

### 6.2 Load Testing Scenarios

| Scenario | Load Profile | Duration | Success Criteria |
|---|---|---|---|
| Normal operation | 10 runs/min | 1 hour | All SLA targets met |
| Peak load | 50 runs/min burst | 15 min | P99 < 2x normal |
| Sustained high | 30 runs/min | 4 hours | No memory leak |
| Stress test | 100 runs/min | 5 min | Graceful failure |
| Recovery test | Peak -> normal | 30 min | Recovery < 5 min |

### 6.3 Performance Regression Tests

| Test | Baseline | Regression Threshold | Frequency |
|---|---|---|---|
| Embedding API latency | P50: 200ms | +50% regression | Per deployment |
| Vector search latency | P99: 500ms | +100% regression | Per deployment |
| Gate decision latency | P90: 120s | +50% regression | Weekly |
| Memory utilization | Peak: 4GB | +30% growth | Weekly |
| Index build time | 2 hours | +100% regression | Per KB update |

### 6.4 Scalability Test Matrix

| Vector Count | Query QPS | Expected P99 | Acceptance P99 | Status |
|---|---|---|---|---|
| 100k | 10 | 50ms | <= 50ms | Required |
| 100k | 50 | 200ms | <= 200ms | Required |
| 1M | 20 | 100ms | <= 100ms | Required |
| 1M | 100 | 500ms | <= 500ms | Required |
| 5M | 50 | 500ms | <= 500ms | Optional |
| 5M | 200 | 2s | <= 2s | Optional |

---

## 7. SLA Targets

### 7.1 Decision Latency SLA

| SLA Class | Metric | Target | Measurement Window | Breach Action |
|---|---|---|---|---|
| Gate decision P90 | Latency | < 120s | Rolling 24h | Alert + investigation |
| Gate decision P99 | Latency | < 300s | Rolling 24h | Critical alert |
| Static gate execution | Latency | < 30s | Per-run | Block timeout |
| State vector generation | Latency | < 10s | Per-run | Skip + warn |

### 7.2 Review Queue SLA

| Metric | Target | Measurement | Alert Threshold | Breach Impact |
|---|---|---|---|---|
| Critical ACK rate | 100% within 15m | Per-item | > 1 breach/hour | Escalation |
| Critical decision rate | 100% within 60m | Per-item | > 1 breach/hour | Fail closed |
| High ACK rate | 95% within 60m | Rolling 24h | > 5% breach | Warning |
| High decision rate | 95% within 240m | Rolling 24h | > 5% breach | Warning |
| Queue drain time | < 4h (High) | Daily average | > 6h average | Scaling review |

### 7.3 Dashboard SLA

| Metric | Target | Measurement | Degradation Threshold |
|---|---|---|---|
| Freshness | < 60s | 95% of updates | > 90s |
| Query latency | < 2s | P95 | > 5s |
| Availability | 99.5% | Monthly | < 99% |
| Writeback latency | < 5s | 99% | > 10s |

### 7.4 Availability Targets

| Component | Target | Downtime Budget | Recovery Time |
|---|---|---|---|
| Gate decision API | 99.5% | 3.6 hours/month | < 5 minutes |
| Vector search | 99.5% | 3.6 hours/month | < 5 minutes |
| Dashboard | 99% | 7.2 hours/month | < 15 minutes |
| Database | 99.9% | 43 minutes/month | < 1 minute |

---

## 8. Budget Management

### 8.1 Token Budget per Run

| Run Type | Token Budget | Embedding Calls | Cost Estimate |
|---|---|---|---|
| Single artifact run | 10k tokens | 1-2 calls | ~$0.0013 |
| Multi-artifact run | 50k tokens | 5-10 calls | ~$0.0065 |
| High-complexity run | 100k tokens | 10-20 calls | ~$0.013 |
| Batch correction run | 200k tokens | 20-50 calls | ~$0.026 |

### 8.2 Monthly Budget Limits

| Category | Limit | Alert Threshold | Hold Threshold | Override Process |
|---|---|---|---|---|
| Total monthly budget | $500 | $400 (80%) | $500 (100%) | Ops/Product approval |
| Embedding API budget | $200 | $160 | $200 | Rate limit reduction |
| Storage budget | $100 | $80 | $100 | Retention extension |
| Compute budget | $100 | $80 | $100 | Scaling reduction |

### 8.3 Cost Alert Configuration

| Alert Level | Threshold | Action | Notification |
|---|---|---|---|
| Warning | 80% ($400) | Log + monitoring | Ops team |
| Hold | 100% ($500) | Pause non-critical ops | Ops + Product |
| Critical | 120% ($600) | Emergency rate limits | All stakeholders |
| Emergency | 150% ($750) | Block all new runs | Incident process |

### 8.4 Cost Optimization Strategies

| Strategy | Savings Potential | Risk | Implementation |
|---|---|---|---|
| Dimension reduction (1536 -> 512) | 50% storage | Recall degradation | Test first |
| Half-precision vectors (float16) | 50% storage | Precision loss | pgvector halfvec |
| TTL-based purging | 30% storage | Audit gap | Retention policy |
| Batch embedding batching | 20% API cost | Latency increase | Queue batching |
| Cached embeddings for similar artifacts | 10-30% API | Freshness delay | Hash-based cache |

---

## 9. Index Performance

### 9.1 HNSW vs IVFFlat Comparison

| Metric | HNSW | IVFFlat | Recommendation |
|---|---|---|---|
| Build time | Hours (higher) | Minutes | IVFFlat for rapid rebuild |
| Query latency | 1-10ms | 10-50ms | HNSW for low-latency |
| Memory usage | 1.5x raw size | 1.1x raw size | IVFFlat for memory-limited |
| Recall@10 | 95-99% | 90-95% | HNSW for quality |
| Scalability | 10M vectors | 1M vectors optimal | HNSW for scale |
| Incremental update | Rebuild required | Add to lists | IVFFlat for frequent updates |

### 9.2 Index Performance Targets

| Vector Count | Index Type | Build Time | Query P99 | Memory |
|---|---|---|---|---|
| 100k | HNSW | < 5 min | 10ms | 0.7 GB |
| 1M | HNSW | < 30 min | 50ms | 7 GB |
| 5M | HNSW | < 2 hours | 100ms | 35 GB |
| 10M | HNSW | < 4 hours | 200ms | 70 GB |

### 9.3 Index Maintenance Performance

| Operation | Frequency | Target Duration | Lock Impact |
|---|---|---|---|
| Incremental insert | Per-run | < 100ms | None (append) |
| Batch insert (1k) | Daily | < 5 min | Brief read lock |
| Full re-index | Monthly | < 4 hours | Full lock |
| Index optimization | Weekly | < 30 min | Read-only |
| Vacuum/cleanup | Daily | < 10 min | Brief lock |

### 9.4 Query Performance Tuning

| Query Type | Default k | Target Latency | Optimization |
|---|---|---|---|
| Taboo proximity | 5 | < 20ms | Pre-filtered index |
| Accepted similarity | 10 | < 50ms | Partitioned search |
| Rejected similarity | 10 | < 50ms | Partitioned search |
| Judgment log search | 20 | < 100ms | Metadata filtering |
| Multi-axis search | 50 total | < 500ms | Parallel queries |

---

## 10. Monitoring Metrics

### 10.1 Core Performance Metrics

| Metric | Collection Method | Resolution | Retention |
|---|---|---|---|
| Gate decision latency | OTel traces | Per-run | 180 days |
| Embedding API latency | API logs | Per-call | 30 days |
| Vector search latency | Query logs | Per-query | 30 days |
| Queue depth | Dashboard metrics | 1 min | 7 days |
| Memory utilization | System metrics | 1 min | 30 days |
| CPU utilization | System metrics | 1 min | 30 days |
| Storage utilization | DB metrics | 5 min | 30 days |

### 10.2 SLA Compliance Metrics

| Metric | Calculation | Reporting | Alert Threshold |
|---|---|---|---|
| Decision SLA compliance | % within target | Daily | < 95% |
| Review ACK SLA compliance | % within deadline | Per-class | < 100% Critical |
| Review decision SLA compliance | % within deadline | Per-class | < 95% High |
| Dashboard freshness SLA | % within 60s | Hourly | < 90% |

### 10.3 Cost Metrics

| Metric | Calculation | Reporting | Alert Threshold |
|---|---|---|---|
| Daily embedding cost | Sum of API calls | Daily | > $20/day |
| Monthly budget utilization | Cumulative / limit | Daily | > 80% |
| Storage growth rate | Daily delta | Weekly | > 5%/week |
| Query cost efficiency | Cost / decision | Weekly | Increasing trend |

### 10.4 Quality Metrics

| Metric | Calculation | Target | Alert Threshold |
|---|---|---|---|
| State vector coverage | % runs with vector | 95% | < 90% |
| Embedding freshness | % embeddings < 24h old | 99% | < 95% |
| Index recall | Offline test | 95% | < 90% |
| Decision consistency | Replay reproducibility | 99% | < 98% |

### 10.5 Alert Thresholds

| Alert | Metric | Threshold | Severity | Action |
|---|---|---|---|---|
| Latency degradation | Gate decision P99 | > 300s | Warning | Investigation |
| Latency critical | Gate decision P99 | > 600s | Critical | Escalation |
| Queue overflow | Queue depth | > 100 | Warning | Scaling review |
| Queue critical | Queue depth | > 200 | Critical | Emergency scaling |
| Memory pressure | Memory % | > 80% | Warning | Scaling |
| Memory critical | Memory % | > 95% | Critical | Emergency action |
| Storage growth | Daily growth | > 5% | Warning | Retention review |
| Cost warning | Budget % | > 80% | Warning | Rate limiting |
| Cost critical | Budget % | > 100% | Critical | Hold operations |

### 10.6 Dashboard KPI Metrics

| KPI | Definition | Target | Reporting Frequency |
|---|---|---|---|
| Review load reduction | % reduction vs baseline | 30% | Weekly |
| Critical miss rate | % missed critical runs | 0% | Daily |
| High miss rate | % missed high runs | < 5% | Daily |
| False escalation rate | % accepted runs held | < 15% | Weekly |
| Queue latency P90 | Review start latency | < 1h (High) | Daily |
| Decision latency P90 | Review resolution | < 4h (High) | Daily |
| Explanation usefulness | Reviewer feedback | > 80% | Monthly |
| Replay reproducibility | % consistent decisions | > 99% | Per-test |

---

## Appendix A: Performance Test Procedures

### A.1 Embedding Latency Test

```
Procedure:
1. Prepare test artifact set (100 items, average 500 tokens)
2. Execute batch embedding with timing instrumentation
3. Record P50, P90, P99 latencies
4. Validate against target thresholds

Pass Criteria:
- P50 < 500ms
- P90 < 2s
- P99 < 5s
- 0% timeout failures
```

### A.2 Vector Search Benchmark

```
Procedure:
1. Load test vector set (1M vectors, 1536d)
2. Execute 10k search queries at k=10
3. Measure query latency distribution
4. Validate recall against ground truth

Pass Criteria:
- P50 < 20ms
- P90 < 100ms
- P99 < 500ms
- Recall@10 > 95%
```

### A.3 Gate Decision End-to-End Test

```
Procedure:
1. Submit 100 test runs via harness adapter
2. Measure full gate decision pipeline latency
3. Validate state against expected outcomes
4. Record per-component latency breakdown

Pass Criteria:
- P50 < 60s
- P90 < 120s
- P99 < 300s
- State vector coverage > 95%
```

---

## Appendix B: Scaling Decision Matrix

### B.1 Component Scaling Triggers

| Current State | Metric Trigger | Scaling Action | New Configuration |
|---|---|---|---|
| 1 encoder worker | Queue > 20 | Add worker | 2 encoder workers |
| 2 encoder workers | Queue > 40 | Add workers | 4 encoder workers |
| Single DB instance | QPS > 100 | Add replica | 2 DB replicas |
| 2 DB replicas | QPS > 200 | Add replicas | 4 DB replicas |
| pgvector | Vectors > 8M | Migrate | Milvus cluster |

### B.2 Cost Scaling Thresholds

| Monthly Budget | Current Utilization | Action | Impact |
|---|---|---|---|
| $500 | 80% ($400) | Rate limit | 10% throughput reduction |
| $500 | 100% ($500) | Hold | Pause new runs |
| $500 | 120% ($600) | Emergency | Block + investigation |

---

## Appendix C: Reference Values

### C.1 Embedding Model Specifications

| Model | Dimensions | Cost/1M tokens | Max Input | Recommended Use |
|---|---|---|---|---|
| text-embedding-3-large | 3072 (default) | $0.13 | 8191 tokens | High precision |
| text-embedding-3-large | 1536 (reduced) | $0.13 | 8191 tokens | MVP default |
| text-embedding-3-large | 512 (reduced) | $0.13 | 8191 tokens | Cost optimization |
| text-embedding-3-small | 1536 | $0.02 | 8191 tokens | Budget alternative |

### C.2 OpenAI Hosted Storage Pricing

| Storage | Monthly Cost | Free Tier | Notes |
|---|---|---|---|
| First 1 GB | Free | 1 GB | Covered by free tier |
| Additional GB | $3/GB/month | - | $0.10/GB/day |
| 100 GB total | ~$300/month | 1 GB free | Not recommended for MVP |

### C.3 pgvector Configuration Reference

```sql
-- Recommended HNSW index configuration
CREATE INDEX ON judgment_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Query with search parameter
SET hnsw.ef_search = 40;
SELECT * FROM judgment_embeddings 
ORDER BY embedding <=> query_vector 
LIMIT 10;
```

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-04-26 | AGF Team | Initial production frozen version |
