# System Design & Architecture

## High-Level Architecture Diagram

```text
[Client / API Gateway]
        │
        ▼ (REST / POST, GET)
[ FastAPI Application (Web Layer) ]
        │      ├── Validates payload (Pydantic)
        │      ├── Checks Rate Limits (Redis)
        │      └── Checks Idempotency & Preferences (Postgres)
        │
        ├──► [ PostgreSQL DB ] (Stores Notifications, Preferences, Webhooks)
        │
        ▼ (Pushes Task)
[ Redis (Message Broker & Cache) ] ◄── Tracks Circuit Breaker state
        │
        ▼ (Consumes Task)
[ Celery Worker (Background Layer) ]
        │
        ├──► (Success) Updates Postgres to 'DELIVERED'
        └──► (Failure) Triggers Circuit Breaker & Exponential Backoff
```

## Database Schema
The database is normalized to separate concerns and ensure data integrity:
1. **`notifications`:** Stores the core delivery data.
   * Fields: `id` (UUID), `user_id`, `channel`, `priority`, `status` (PENDING, SENT, DELIVERED, FAILED), `payload`, `created_at`.
2. **`user_preferences`:** Tracks user channel opt-outs to guarantee compliance.
   * Fields: `id`, `user_id`, `channel`, `is_enabled` (Boolean). 
3. **`webhooks`:** Stores external URLs for delivery callbacks (Bonus Feature).
   * Fields: `id`, `url`.

## Handling Failures and Retries
* **Transient Failures:** Handled by Celery's built-in `@app.task(bind=True, max_retries=3)`. When a mocked provider times out, the task throws an exception and retries using exponential backoff (`countdown=2 ** retries`).
* **Systemic Outages:** Handled via a Redis-backed **Circuit Breaker** pattern. If an external provider fails 3 consecutive times, Redis trips the circuit, instantly failing subsequent worker tasks for 60 seconds to prevent queue bottlenecks.

## System Scalability
The system is designed for horizontal scaling to support 1000+ req/sec:
* **Stateless API:** The FastAPI pods hold no local state. They can be scaled infinitely behind a load balancer (as demonstrated in the Kubernetes deployment manifests).
* **O(1) Rate Limiting:** Redis handles sliding-window rate limiting in constant time, meaning API ingestion speed is never bottlenecked by database locks.
* **Worker Scaling:** As the Redis queue grows, more Celery worker containers can be spun up independently of the web API to handle the backlog.

## Architectural Trade-offs
* **PostgreSQL vs. NoSQL (MongoDB):** A relational database was chosen over a NoSQL document store. While NoSQL handles massive un-structured writes well, tracking exact delivery states, enforcing unique idempotency constraints, and running grouped aggregation queries for the `/analytics` endpoint requires the strict ACID compliance of SQL.
* **Redis vs. RabbitMQ:** Redis was chosen over RabbitMQ. While RabbitMQ offers more complex routing topologies, Redis keeps the infrastructure footprint small by acting simultaneously as the Celery broker, the rate-limiter cache, and the circuit-breaker state store.