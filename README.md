# Backend Notification Service

A robust, highly scalable, asynchronous notification microservice built to handle 1000+ requests per second. It supports multi-channel delivery, user preferences, retry mechanisms, and rate limiting.

## Project Overview
This service ingests notification requests via a RESTful API, validates the payloads, checks user opt-in/opt-out preferences, and queues the messages for asynchronous delivery. It features strict idempotency to prevent duplicate messages and includes bonus implementations like a Batch API, Analytics tracking, and a Circuit Breaker.

## Tech Stack & Rationale
* **FastAPI (Python):** Chosen for its exceptional asynchronous performance, built-in Pydantic validation, and automatic OpenAPI documentation generation.
* **PostgreSQL:** Chosen as the primary database for strict ACID compliance, ensuring that delivery statuses and user preferences remain consistent and reliable.
* **Redis:** Acts as a high-speed, in-memory datastore. It is used simultaneously as the Celery message broker, the rate-limiting counter, and the state manager for the circuit breaker.
* **Celery:** Used for distributed task queueing to ensure the API never blocks while waiting for slow third-party email/SMS providers.
* **Docker & docker-compose:** Containerizes the application and its dependencies to ensure environment consistency across local development and production.

## Setup Instructions (Local Development)
1. Clone this repository to your local machine.
2. Ensure you have Docker and Docker Desktop installed and running.
3. Open a terminal in the root directory of the project and run:

```bash
docker-compose up -d --build
```

4. The API will be available at `http://localhost:8000`.

## API Documentation
Once the server is running, interactive API documentation (Swagger UI) is automatically available at:
**[http://localhost:8000/docs](http://localhost:8000/docs)**

## How to Run Tests
The project includes a comprehensive test suite using `pytest` and `httpx`. To run the tests inside the isolated Docker environment, execute:

```bash
docker-compose exec api pytest test_main.py -v
```

## Assumptions Made
* **Authentication/Authorization:** Assumed to be handled by an upstream API Gateway. This service relies on internal routing and does not implement JWT/OAuth natively.
* **Template Storage:** Assumed to be stored in-memory via a Python dictionary for demonstration purposes, rather than querying a separate template database.
* **Third-Party Providers:** Assumed to be mocked. The worker simulates network latency and random failure rates to trigger the Celery retry logic.