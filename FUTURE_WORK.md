# Future work

[`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) is the source of truth for the current typed crawl and influencer workflow.

## Implemented

- [x] Pace-Unit accepts complete typed `content_crawl` and `influencer_discovery` requests.
- [x] DCT owns influencer discovery, evaluation, task state, durable queue processing, candidate persistence, and evidence persistence.
- [x] Influencer requests normalize `field + related_terms` through an in-memory `TopicBrief` and pass the field-first term list to every discovery source.
- [x] X author and scroll limits remain configuration-driven; public discovery keeps its configured templates and per-article limit.
- [x] Influencer results do not publish to the article response queue. Pace proxies status to DCT.
- [x] Explicit dashboard export supports freshness filtering, flag preservation, empty-result rejection, and `--dry-run`.
- [x] Legacy influencer collections remain available for rollback but are not written by the new runtime.
- [x] Unit tests cover request validation, normalization, source propagation, evaluator rules, candidate identity/freshness, evidence, resume, status transitions, worker failures, response routing, and export mapping.

## Remaining work

### Live validation

- [ ] Run one real command-to-status influencer task with the configured X session, SQS, and DCT MongoDB.
- [ ] Run one dashboard export dry run and verify the selected `company_id`, `platform`, `company_domain`, and freshness window.
- [ ] Run one non-dry export against a staging dashboard document and verify existing `status` and `relevancy` flags remain intact.
- [ ] Verify lock contention, X access failure, redrive/DLQ, and resume behavior in an isolated queue environment.

### Frontend/API adoption

- [ ] Update the frontend influencer form to submit the complete request contract to `POST /api/crawl/`.
- [ ] Poll `GET /api/crawl/<job_id>/` and display DCT states and progress counters.
- [ ] Replace any remaining use of legacy `POST /api/search/` for new crawl requests.

### Operations

- [ ] Run DCT command consumption and Pace article response consumption under supervised services.
- [ ] Add SQS/DLQ alarms and a documented operator procedure for `--resume` and dashboard export.
- [ ] Add isolated integration tests using test queues and test MongoDB databases.

## Ownership

- **Data-Crawler-Task:** content crawling, influencer discovery, evaluation, persistence, task status, durable queues, evidence, and dashboard export.
- **Pace-Unit:** typed request acceptance, `crawl_jobs` facade, article response processing, article AI persistence, and status proxying.
- **Dashboard MongoDB:** updated only by the explicit DCT export command.
