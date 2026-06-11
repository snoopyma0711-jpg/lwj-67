from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Zone, Sensor
from app.schemas import InitRequest, ZoneConfig

router = APIRouter(prefix="/api/init", tags=["初始化"])


@router.post("/zones", summary="导入区域和货架配置")
def init_zones(req: InitRequest, db: Session = Depends(get_db)):
    for zone_cfg in req.zones:
        existing = db.query(Zone).filter(Zone.name == zone_cfg.name).first()
        if existing:
            db.query(Sensor).filter(Sensor.zone_id == existing.id).delete()
            existing.temp_lower = zone_cfg.temp_lower
            existing.temp_upper = zone_cfg.temp_upper
            existing.humidity_lower = zone_cfg.humidity_lower
            existing.humidity_upper = zone_cfg.humidity_upper
            for sid in zone_cfg.sensor_ids:
                db.add(Sensor(sensor_id=sid, zone_id=existing.id))
        else:
            zone = Zone(
                name=zone_cfg.name,
                temp_lower=zone_cfg.temp_lower,
                temp_upper=zone_cfg.temp_upper,
                humidity_lower=zone_cfg.humidity_lower,
                humidity_upper=zone_cfg.humidity_upper,
            )
            db.add(zone)
            db.flush()
            for sid in zone_cfg.sensor_ids:
                db.add(Sensor(sensor_id=sid, zone_id=zone.id))

    db.commit()
    return {"message": "初始化成功", "zone_count": len(req.zones)}
