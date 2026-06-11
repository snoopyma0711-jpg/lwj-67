from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.database import get_db
from app.models import SensorData
from app.schemas import DataUploadRequest, DataUploadResponse
from app.services.alert_engine import check_and_update_alerts

router = APIRouter(prefix="/api/data", tags=["数据上报"])


@router.post("/upload", response_model=DataUploadResponse, summary="传感器数据批量上报")
def upload_data(req: DataUploadRequest, db: Session = Depends(get_db)):
    duplicates = 0
    received = 0

    sorted_items = sorted(req.data, key=lambda x: x.timestamp)

    seen_keys = set()
    for item in sorted_items:
        key = (item.sensor_id, item.timestamp)
        if key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(key)

        stmt = sqlite_insert(SensorData).values(
            sensor_id=item.sensor_id,
            temperature=item.temperature,
            humidity=item.humidity,
            timestamp=item.timestamp,
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["sensor_id", "timestamp"],
        )
        result = db.execute(stmt)
        if result.rowcount == 0:
            duplicates += 1
        else:
            received += 1
            check_and_update_alerts(db, item.sensor_id, item.temperature, item.humidity, item.timestamp)
            db.flush()

    db.commit()
    return DataUploadResponse(received=received, duplicates=duplicates)
