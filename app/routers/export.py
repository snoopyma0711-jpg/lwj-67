from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Zone, Sensor, SensorData
from app.schemas import ExportListResponse, ExportDataItem

router = APIRouter(prefix="/api/export", tags=["数据导出"])

MAX_TIME_RANGE_HOURS = 24
MAX_RECORD_COUNT = 100000


@router.get("/sensor-data", summary="导出传感器原始数据")
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
            return ExportListResponse(zone_name=zone_name, total=0, data=[])
        else:
            return PlainTextResponse(
                content="传感器编号,温度,湿度,采集时间,是否超标\n",
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={zone_name}_export.csv"},
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

    if format == "list":
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
        return ExportListResponse(zone_name=zone_name, total=len(data), data=data)
    else:
        csv_lines = ["传感器编号,温度,湿度,采集时间,是否超标"]
        for row in rows:
            is_exceeded = (
                row.temperature < temp_lower
                or row.temperature > temp_upper
                or row.humidity < humidity_lower
                or row.humidity > humidity_upper
            )
            csv_lines.append(
                f"{row.sensor_id},{row.temperature},{row.humidity},{row.timestamp.isoformat()},{1 if is_exceeded else 0}"
            )
        csv_content = "\n".join(csv_lines) + "\n"
        filename = f"{zone_name}_{start_time.strftime('%Y%m%d%H%M%S')}_{end_time.strftime('%Y%m%d%H%M%S')}.csv"
        return PlainTextResponse(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
