from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Alert, Zone, Sensor, SensorData
from app.schemas import (
    AlertItem, AlertListResponse, ResolveAlertRequest,
    AlertStatsResponse, ZoneAlertStats,
    SensorHealthItem, SensorHealthDashboardResponse,
)

router = APIRouter(prefix="/api/alerts", tags=["告警管理"])


@router.get("", response_model=AlertListResponse, summary="告警列表查询")
def list_alerts(
    zone_name: str = Query(None, description="区域名称"),
    status: str = Query(None, description="状态筛选: unprocessed / processed"),
    level: str = Query(None, description="等级筛选: 警告 / 紧急"),
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

    if level:
        query = query.filter(Alert.level == level)

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
            level=a.level,
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
    alert.resolved_at = datetime.utcnow()
    alert.resolved_note = req.resolved_note
    db.commit()
    return {"message": "告警已处理", "alert_id": alert_id}


@router.get("/stats", response_model=AlertStatsResponse, summary="告警统计")
def alert_stats(
    start_time: datetime = Query(..., description="统计开始时间"),
    end_time: datetime = Query(..., description="统计结束时间"),
    db: Session = Depends(get_db),
):
    zones = db.query(Zone).all()
    stats = []

    for zone in zones:
        alerts = db.query(Alert).filter(
            and_(
                Alert.zone_id == zone.id,
                Alert.started_at >= start_time,
                Alert.started_at <= end_time,
            )
        ).all()

        normal_count = sum(1 for a in alerts if a.level == "警告")
        urgent_count = sum(1 for a in alerts if a.level == "紧急")

        processed_alerts = [a for a in alerts if a.status == "processed" and a.resolved_at]
        if processed_alerts:
            total_response_seconds = sum(
                (a.resolved_at - a.started_at).total_seconds()
                for a in processed_alerts
            )
            avg_response = total_response_seconds / len(processed_alerts)
        else:
            avg_response = None

        stats.append(ZoneAlertStats(
            zone_name=zone.name,
            normal_count=normal_count,
            urgent_count=urgent_count,
            avg_response_seconds=avg_response,
        ))

    return AlertStatsResponse(stats=stats)


@router.get("/health-dashboard", response_model=SensorHealthDashboardResponse, summary="传感器健康度看板")
def sensor_health_dashboard(
    zone_name: str = Query(..., description="区域名称"),
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.name == zone_name).first()
    if not zone:
        return SensorHealthDashboardResponse(zone_name=zone_name, sensors=[])

    sensors = db.query(Sensor).filter(Sensor.zone_id == zone.id).all()
    if not sensors:
        return SensorHealthDashboardResponse(zone_name=zone_name, sensors=[])

    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    expected_reports = 720
    min_reports_threshold = int(expected_reports * 0.8)

    result = []
    for sensor in sensors:
        sensor_id = sensor.sensor_id

        recent_data = db.query(SensorData).filter(
            and_(
                SensorData.sensor_id == sensor_id,
                SensorData.timestamp >= one_hour_ago,
            )
        ).order_by(SensorData.timestamp.asc()).all()

        report_count = len(recent_data)
        last_report_time = recent_data[-1].timestamp if recent_data else None

        exceed_count = 0
        for data in recent_data:
            temp_exceeded = data.temperature < zone.temp_lower or data.temperature > zone.temp_upper
            humidity_exceeded = data.humidity < zone.humidity_lower or data.humidity > zone.humidity_upper
            if temp_exceeded or humidity_exceeded:
                exceed_count += 1

        if report_count < min_reports_threshold:
            status = "离线"
            score = 0
        elif report_count > 0 and exceed_count / report_count > 0.5:
            status = "异常"
            normal_count = report_count - exceed_count
            score = int((normal_count / report_count) * 100)
        else:
            status = "正常"
            score = 100

        result.append(SensorHealthItem(
            sensor_id=sensor_id,
            status=status,
            score=score,
            report_count=report_count,
            exceed_count=exceed_count,
            last_report_time=last_report_time,
        ))

    return SensorHealthDashboardResponse(zone_name=zone_name, sensors=result)
