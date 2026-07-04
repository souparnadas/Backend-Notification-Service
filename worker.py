import os
import time
import random
import redis
from celery import Celery

# Connect Celery to the Redis container
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
celery_app = Celery("notification_worker", broker=REDIS_URL)

# Connect a standard Redis client for the Circuit Breaker
redis_client = redis.Redis(host='redis', port=6379, db=1)

# CIRCUIT BREAKER LOGIC
def check_circuit_breaker(r_client):
    fails = r_client.get("circuit_fails")
    if fails and int(fails) >= 3:
        raise Exception("CIRCUIT BREAKER OPEN: External provider is down. Fast failing.")

def record_failure(r_client):
    r_client.incr("circuit_fails")
    r_client.expire("circuit_fails", 60) # Reset circuit after 60 seconds

def reset_circuit(r_client):
    r_client.set("circuit_fails", 0)

# MOCK PROVIDERS
class BaseProvider:
    def send(self, target, content):
        raise NotImplementedError

class MockEmailProvider(BaseProvider):
    def send(self, target, content):
        time.sleep(0.5) # Simulate network delay
        if random.random() < 0.2: # 20% chance to fail to test retries
            raise Exception("Email Provider Timeout")
        return True

providers = {
    "EMAIL": MockEmailProvider(),
    # SMS and PUSH logic would go here
}
# CELERY TASK
@celery_app.task(bind=True, max_retries=3)
def process_notification(self, notification_id: str, channel: str, content: str):
    provider = providers.get(channel)
    if not provider:
        return

    try:
        # 1. Check Circuit Breaker before attempting to send
        check_circuit_breaker(redis_client)
        
        success = provider.send("user_target", content)
        if success:
            # 2. Reset Circuit Breaker on success
            reset_circuit(redis_client)
            print(f"[{notification_id}] Successfully sent via {channel}")
            
            # --- NEW CODE TO UPDATE POSTGRESQL ---
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            
            from models import Notification
            from main import SessionLocal
            
            db = SessionLocal()
            try:
                record = db.query(Notification).filter(Notification.id == notification_id).first()
                if record:
                    record.status = "DELIVERED"
                    db.commit()
            except Exception as e:
                print(f"Database update error: {e}")
                db.rollback()
            finally:
                db.close()
            # -------------------------------------
            
    except Exception as e:
        # 3. Record failure and trigger exponential backoff retry
        record_failure(redis_client)
        print(f"[{notification_id}] Failed to send: {e}")
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
