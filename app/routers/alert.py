from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, Zone
from app.schemas import AlertItem, AlertListResponse, ResolveAlertRequest

router = APIRouter(prefix="/api/alerts", tags=["告警管理"])


@router.get("", response_model=AlertListResponse, summary="告警列表查询")
def list_alerts(
    zone_name: str = Query(None, description="区域名称"),
    status: str = Query(None, description="状态筛选: unprocessed / processed"),
    db: Session = Depends(get_db),
):
    query = db.query(Alert)

    if zone_name:
        zone = db.query(Zone).filter(Zone.name == zone_name).first()
        if zone:
            query = query.filter(Alert.zone_id == zone.id)
        else:
            return AlertListResponse(total=0, alerts=[])

    if status:
        query = query.filter(Alert.status == status)

    query = query.order_by(Alert.id.desc())
    total = query.count()
    alerts = query.all()

    zone_map = {z.id: z.name for z in db.query(Zone).all()}

    items = []
    for a in alerts:
        items.append(AlertItem(
            id=a.id,
            zone_name=zone_map.get(a.zone_id, "unknown"),
            sensor_id=a.sensor_id,
            alert_type=a.alert_type,
            started_at=a.started_at,
            duration_seconds=a.duration_seconds,
            status=a.status,
            resolved_note=a.resolved_note,
        ))

    return AlertListResponse(total=total, alerts=items)


@router.put("/{alert_id}/resolve", summary="标记告警为已处理")
def resolve_alert(alert_id: int, req: ResolveAlertRequest, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return {"message": "告警记录不存在"}

    alert.status = "processed"
    alert.resolved_note = req.resolved_note
    db.commit()
    return {"message": "告警已处理", "alert_id": alert_id}
