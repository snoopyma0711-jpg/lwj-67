from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from urllib.parse import quote
from app.database import get_db
from app.models import Zone, Sensor, SensorData
from app.schemas import ExportDataItem

router = APIRouter(prefix="/api/export", tags=["数据导出"])

MAX_TIME_RANGE_HOURS = 24
MAX_RECORD_COUNT = 100000


@router.get("/sensor-data", response_model=list[ExportDataItem], summary="导出传感器原始数据")
def export_sensor_data(
    zone_name: str = Query(..., description="区域名称"),
    start_time: datetime = Query(..., description="开始时间"),
    end_time: datetime = Query(..., description="结束时间"),
    format: str = Query("list", description="导出格式：list 或 file", enum=["list", "file"]),
    db: Session = Depends(get_db),
):
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="结束时间必须大于开始时间")

    time_range = end_time - start_time
    if time_range > timedelta(hours=MAX_TIME_RANGE_HOURS):
        raise HTTPException(
            status_code=400,
            detail=f"时间范围不能超过{MAX_TIME_RANGE_HOURS}小时，请缩小时间范围",
        )

    zone = db.query(Zone).filter(Zone.name == zone_name).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"区域 {zone_name} 不存在")

    sensor_ids = [s.sensor_id for s in db.query(Sensor).filter(Sensor.zone_id == zone.id).all()]

    if not sensor_ids:
        if format == "list":
            return []
        else:
            csv_content = "\ufeff传感器编号,温度,湿度,采集时间,是否超标\n"
            filename = f"{zone_name}_{start_time.strftime('%Y%m%d%H%M%S')}_{end_time.strftime('%Y%m%d%H%M%S')}.csv"
            return Response(
                content=csv_content.encode("utf-8"),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                    "Content-Type": "text/csv; charset=utf-8",
                },
            )

    count = (
        db.query(SensorData)
        .filter(
            SensorData.sensor_id.in_(sensor_ids),
            SensorData.timestamp >= start_time,
            SensorData.timestamp <= end_time,
        )
        .count()
    )

    if count > MAX_RECORD_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"导出数据量({count}条)超过最大限制({MAX_RECORD_COUNT}条)，请缩小时间范围",
        )

    rows = (
        db.query(SensorData)
        .filter(
            SensorData.sensor_id.in_(sensor_ids),
            SensorData.timestamp >= start_time,
            SensorData.timestamp <= end_time,
        )
        .order_by(SensorData.timestamp.asc())
        .all()
    )

    temp_lower = zone.temp_lower
    temp_upper = zone.temp_upper
    humidity_lower = zone.humidity_lower
    humidity_upper = zone.humidity_upper

    data = []
    for row in rows:
        is_exceeded = (
            row.temperature < temp_lower
            or row.temperature > temp_upper
            or row.humidity < humidity_lower
            or row.humidity > humidity_upper
        )
        data.append(
            ExportDataItem(
                sensor_id=row.sensor_id,
                temperature=row.temperature,
                humidity=row.humidity,
                timestamp=row.timestamp,
                is_exceeded=is_exceeded,
            )
        )

    if format == "list":
        return data
    else:
        csv_lines = ["\ufeff传感器编号,温度,湿度,采集时间,是否超标"]
        for item in data:
            csv_lines.append(
                f"{item.sensor_id},{item.temperature},{item.humidity},{item.timestamp.isoformat()},{1 if item.is_exceeded else 0}"
            )
        csv_content = "\n".join(csv_lines) + "\n"
        filename = f"{zone_name}_{start_time.strftime('%Y%m%d%H%M%S')}_{end_time.strftime('%Y%m%d%H%M%S')}.csv"
        return Response(
            content=csv_content.encode("utf-8"),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                "Content-Type": "text/csv; charset=utf-8",
            },
        )
