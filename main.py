from fastapi import FastAPI, HTTPException, Depends
import uuid
import redis
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from models import Notification, UserPreference, NotificationStatus
from schemas import NotificationRequest, NotificationResponse, PreferenceUpdate
from worker import process_notification
from sqlalchemy import func
from models import Webhook
from schemas import BatchNotificationRequest, WebhookCreate

app = FastAPI(title="Notification Service API")

# Connect to Redis and Postgres containers
REDIS_URL = os.getenv("REDIS_URL", "redis") # Docker service name is just "redis" for the host
redis_client = redis.Redis(host='redis', port=6379, db=1)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@db:5432/notification_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_rate_limit(user_id: str):
    key = f"rate_limit:{user_id}"
    current = redis_client.get(key)
    if current and int(current) >= 100:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
    pipe = redis_client.pipeline()
    pipe.incr(key)
    if not current:
        pipe.expire(key, 3600)
    pipe.execute()

def render_template(template_name: str, variables: dict) -> str:
    mock_template = "Hello {name}, your order {order_id} has shipped."
    try:
        return mock_template.format(**variables)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing template variable: {e}")

@app.post("/notifications", response_model=NotificationResponse, status_code=202)
def send_notification(req: NotificationRequest, db: Session = Depends(get_db)):
    check_rate_limit(req.user_id)
    
    if req.idempotency_key:
        existing = db.query(Notification).filter_by(idempotency_key=req.idempotency_key).first()
        if existing:
            return {"id": existing.id, "status": existing.status, "message": "Duplicate acknowledged"}
            
    pref = db.query(UserPreference).filter_by(user_id=req.user_id, channel=req.channel).first()
    if pref and not pref.is_enabled:
        raise HTTPException(status_code=403, detail="User opted out of this channel")
        
    content = render_template(req.template_name, req.variables)
    
    notif_id = str(uuid.uuid4())
    new_notif = Notification(
        id=notif_id,
        user_id=req.user_id,
        channel=req.channel,
        priority=req.priority,
        payload={"content": content},
        idempotency_key=req.idempotency_key
    )
    db.add(new_notif)
    db.commit()
    
    process_notification.apply_async(args=[notif_id, req.channel.value, content])
    return {"id": notif_id, "status": NotificationStatus.PENDING, "message": "Queued"}

@app.get("/notifications/{id}")
def get_notification_status(id: str, db: Session = Depends(get_db)):
    notif = db.query(Notification).filter_by(id=id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": notif.id, "status": notif.status, "retry_count": notif.retry_count}

@app.get("/users/{user_id}/notifications")
def get_user_notifications(user_id: str, db: Session = Depends(get_db)):
    notifs = db.query(Notification).filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    return {"user_id": user_id, "notifications": notifs}

@app.post("/users/{user_id}/preferences")
def set_user_preferences(user_id: str, pref: PreferenceUpdate, db: Session = Depends(get_db)):
    existing = db.query(UserPreference).filter_by(user_id=user_id, channel=pref.channel).first()
    if existing:
        existing.is_enabled = pref.is_enabled
    else:
        new_pref = UserPreference(user_id=user_id, channel=pref.channel, is_enabled=pref.is_enabled)
        db.add(new_pref)
    db.commit()
    return {"message": "Preferences updated"}

@app.get("/users/{user_id}/preferences")
def get_user_preferences(user_id: str, db: Session = Depends(get_db)):
    prefs = db.query(UserPreference).filter_by(user_id=user_id).all()
    return {"user_id": user_id, "preferences": prefs}
@app.post("/notifications/batch", status_code=202)
def send_batch_notifications(req: BatchNotificationRequest, db: Session = Depends(get_db)):
    notif_ids = []
    for uid in req.user_ids:
        # Check if user opted out
        pref = db.query(UserPreference).filter_by(user_id=uid, channel=req.channel).first()
        if pref and not pref.is_enabled:
            continue
            
        content = render_template(req.template_name, req.variables)
        notif_id = str(uuid.uuid4())
        
        new_notif = Notification(
            id=notif_id, user_id=uid, channel=req.channel,
            priority=req.priority, payload={"content": content}
        )
        db.add(new_notif)
        notif_ids.append(notif_id)
        process_notification.apply_async(args=[notif_id, req.channel.value, content])
        
    db.commit()
    return {"queued_count": len(notif_ids), "notification_ids": notif_ids}

@app.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    # Group notifications by channel and status to get summary stats
    stats = db.query(
        Notification.channel, Notification.status, func.count(Notification.id)
    ).group_by(Notification.channel, Notification.status).all()
    
    result = {}
    for channel, status, count in stats:
        ch_name, st_name = channel.name, status.name
        if ch_name not in result:
            result[ch_name] = {}
        result[ch_name][st_name] = count
        
    return {"analytics": result}

@app.post("/webhooks")
def register_webhook(webhook: WebhookCreate, db: Session = Depends(get_db)):
    existing = db.query(Webhook).filter_by(url=webhook.url).first()
    if not existing:
        new_hook = Webhook(url=webhook.url)
        db.add(new_hook)
        db.commit()
    return {"message": "Webhook registered successfully"}