from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Zone, Sensor, SensorData
from app.schemas import MinuteDataPoint, HistoryQueryResponse

router = APIRouter(prefix="/api/query", tags=["历史查询"])


@router.get("/history", response_model=HistoryQueryResponse, summary="按区域和时间范围查询历史数据")
def query_history(
    zone_name: str = Query(..., description="区域名称"),
    start_time: datetime = Query(..., description="开始时间"),
    end_time: datetime = Query(..., description="结束时间"),
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.name == zone_name).first()
    if not zone:
        return HistoryQueryResponse(zone_name=zone_name, data=[])

    sensor_ids = [s.sensor_id for s in db.query(Sensor).filter(Sensor.zone_id == zone.id).all()]
    if not sensor_ids:
        return HistoryQueryResponse(zone_name=zone_name, data=[])

    minute_start = start_time.replace(second=0, microsecond=0)
    minute_end = end_time.replace(second=0, microsecond=0)

    placeholders = ",".join([f":sid{i}" for i in range(len(sensor_ids))])
    params = {f"sid{i}": sid for i, sid in enumerate(sensor_ids)}
    params["minute_start"] = minute_start
    params["minute_end"] = minute_end
    params["minute_end_plus"] = minute_end + timedelta(minutes=1)

    sql = text(f"""
        SELECT
            strftime('%Y-%m-%d %H:%M', timestamp) AS minute,
            AVG(temperature) AS avg_temperature,
            AVG(humidity) AS avg_humidity
        FROM sensor_data
        WHERE sensor_id IN ({placeholders})
          AND timestamp >= :minute_start
          AND timestamp < :minute_end_plus
        GROUP BY minute
        ORDER BY minute
    """)

    rows = db.execute(sql, params).fetchall()

    data_map = {}
    for row in rows:
        dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
        data_map[dt] = MinuteDataPoint(
            minute=dt,
            avg_temperature=round(row[1], 2),
            avg_humidity=round(row[2], 2),
        )

    result = []
    current = minute_start
    while current <= minute_end:
        if current in data_map:
            result.append(data_map[current])
        else:
            interpolated = _interpolate(current, data_map)
            result.append(interpolated)
        current += timedelta(minutes=1)

    return HistoryQueryResponse(zone_name=zone_name, data=result)


def _interpolate(target: datetime, data_map: dict) -> MinuteDataPoint:
    before_point = None
    after_point = None

    delta = timedelta(minutes=1)
    t = target - delta
    while t >= min(data_map.keys(), default=target):
        if t in data_map:
            before_point = data_map[t]
            break
        t -= delta

    t = target + delta
    max_key = max(data_map.keys(), default=target)
    while t <= max_key:
        if t in data_map:
            after_point = data_map[t]
            break
        t += delta

    if before_point and after_point:
        total = (after_point.minute - before_point.minute).total_seconds()
        ratio = (target - before_point.minute).total_seconds() / total if total > 0 else 0.5
        return MinuteDataPoint(
            minute=target,
            avg_temperature=round(before_point.avg_temperature + ratio * (after_point.avg_temperature - before_point.avg_temperature), 2),
            avg_humidity=round(before_point.avg_humidity + ratio * (after_point.avg_humidity - before_point.avg_humidity), 2),
        )
    elif before_point:
        return MinuteDataPoint(minute=target, avg_temperature=before_point.avg_temperature, avg_humidity=before_point.avg_humidity)
    elif after_point:
        return MinuteDataPoint(minute=target, avg_temperature=after_point.avg_temperature, avg_humidity=after_point.avg_humidity)
    else:
        return MinuteDataPoint(minute=target, avg_temperature=0.0, avg_humidity=0.0)
