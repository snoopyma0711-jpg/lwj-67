from sqlalchemy.orm import Session
from app.models import Sensor, Zone, ConsecutiveExceed, Alert
from datetime import datetime


def check_and_update_alerts(db: Session, sensor_id: str, temperature: float, humidity: float, timestamp: datetime):
    sensor = db.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
    if not sensor:
        return

    zone = db.query(Zone).filter(Zone.id == sensor.zone_id).first()
    if not zone:
        return

    temp_exceeded = temperature < zone.temp_lower or temperature > zone.temp_upper
    humidity_exceeded = humidity < zone.humidity_lower or humidity > zone.humidity_upper

    _process_exceed_type(
        db, sensor_id, zone, "temperature",
        temp_exceeded, timestamp,
    )
    _process_exceed_type(
        db, sensor_id, zone, "humidity",
        humidity_exceeded, timestamp,
    )


def _process_exceed_type(
    db: Session, sensor_id: str, zone: Zone,
    exceed_type: str, is_exceeded: bool, timestamp: datetime,
):
    record = db.query(ConsecutiveExceed).filter(
        ConsecutiveExceed.sensor_id == sensor_id,
        ConsecutiveExceed.exceed_type == exceed_type,
    ).first()

    if is_exceeded:
        if record is None:
            record = ConsecutiveExceed(
                sensor_id=sensor_id,
                exceed_type=exceed_type,
                count=1,
                first_exceeded_at=timestamp,
            )
            db.add(record)
        else:
            record.count += 1
            if record.count == 1:
                record.first_exceeded_at = timestamp

        if record.count >= 3:
            duration = int((timestamp - record.first_exceeded_at).total_seconds())
            alert = Alert(
                zone_id=zone.id,
                sensor_id=sensor_id,
                alert_type=exceed_type,
                started_at=record.first_exceeded_at,
                duration_seconds=duration,
                status="unprocessed",
            )
            db.add(alert)
            record.count = 0
            record.first_exceeded_at = None
    else:
        if record is not None:
            record.count = 0
            record.first_exceeded_at = None
