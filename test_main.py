import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Import your FastAPI app and database models
from main import app, get_db
from models import NotificationStatus

client = TestClient(app)

# ==========================================
# FIXTURES & MOCKS
# ==========================================
@pytest.fixture
def mock_db():
    """Creates a mock SQLAlchemy database session."""
    db = MagicMock()
    return db

@pytest.fixture
def override_db(mock_db):
    """Overrides the FastAPI dependency injection with our mock database."""
    app.dependency_overrides[get_db] = lambda: mock_db
    yield mock_db
    app.dependency_overrides.clear()


# ==========================================
# CORE FUNCTIONALITY & ENDPOINT TESTS
# ==========================================

@patch("main.redis_client")
@patch("main.process_notification")
def test_send_notification_success(mock_celery, mock_redis, override_db):
    """Test that a valid notification request is successfully queued."""
    # Mock rate limiting (Redis returns None, meaning no limit hit)
    mock_redis.get.return_value = None
    
    # Mock database (No idempotency key match, no opt-out record)
    override_db.query.return_value.filter_by.return_value.first.return_value = None

    payload = {
        "user_id": "test_user_123",
        "channel": "EMAIL",
        "priority": "NORMAL",
        "template_name": "welcome",
        "variables": {"name": "Alice", "order_id": "456"},
        "idempotency_key": "unique-key-1"
    }

    response = client.post("/notifications", json=payload)
    
    assert response.status_code == 202
    assert response.json()["status"] == "PENDING"
    assert "id" in response.json()
    
    # Verify Celery task was actually triggered asynchronously
    mock_celery.apply_async.assert_called_once()


@patch("main.redis_client")
def test_send_notification_user_opted_out(mock_redis, override_db):
    """Test that a 403 Forbidden is raised if the user opted out of the channel."""
    mock_redis.get.return_value = None
    
    # Mock the UserPreference record to simulate an explicit opt-out (is_enabled = False)
    mock_preference = MagicMock()
    mock_preference.is_enabled = False
    
    # FIX: We use side_effect (not side_with) so the first DB check (idempotency) 
    # returns None, and the second DB check (preferences) returns the opt-out status.
    override_db.query.return_value.filter_by.return_value.first.side_effect = [None, mock_preference]

    payload = {
        "user_id": "souparna",
        "channel": "EMAIL",
        "priority": "NORMAL",
        "template_name": "string",
        "variables": {},
        "idempotency_key": "test-block-001"
    }

    response = client.post("/notifications", json=payload)
    
    assert response.status_code == 403
    assert response.json()["detail"] == "User opted out of this channel"

@patch("main.redis_client")
def test_send_notification_idempotency(mock_redis, override_db):
    """Test that duplicate requests with the same idempotency key are acknowledged without processing."""
    mock_redis.get.return_value = None
    
    # Mock an existing notification record already saved in DB
    mock_existing = MagicMock()
    mock_existing.id = "existing-uuid"
    mock_existing.status = NotificationStatus.PENDING
    
    override_db.query.return_value.filter_by.return_value.first.return_value = mock_existing

    payload = {
        "user_id": "test_user_123",
        "channel": "EMAIL",
        "priority": "NORMAL",
        "template_name": "welcome",
        "variables": {"name": "Alice", "order_id": "456"},
        "idempotency_key": "duplicate-key"
    }

    response = client.post("/notifications", json=payload)
    
    assert response.status_code == 202
    assert response.json()["message"] == "Duplicate acknowledged"
    assert response.json()["id"] == "existing-uuid"


@patch("main.redis_client")
def test_rate_limiting_exceeded(mock_redis, override_db):
    """Test that hitting the API 100+ times triggers a 429 Rate Limit Exceeded error."""
    # Simulate Redis indicating that the user has already sent 100 messages
    mock_redis.get.return_value = b"100"

    payload = {
        "user_id": "spammer_user",
        "channel": "SMS",
        "priority": "HIGH",
        "template_name": "alert",
        "variables": {}
    }

    response = client.post("/notifications", json=payload)
    
    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"


def test_get_notification_status_not_found(override_db):
    """Test that looking up a non-existent notification ID returns a 404."""
    override_db.query.return_value.filter_by.return_value.first.return_value = None

    response = client.get("/notifications/fake-id-abc")
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"