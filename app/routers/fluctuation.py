from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import Zone, Sensor, SensorData
from app.schemas import (
    FluctuationAnalysisResponse,
    FluctuationSensorItem,
    FluctuationDetailResponse,
    FluctuationDetailItem,
    FluctuationDataPoint,
)

router = APIRouter(prefix="/api/fluctuation", tags=["异常波动分析"])


@router.get("/analysis", response_model=FluctuationAnalysisResponse, summary="传感器异常波动分析")
def fluctuation_analysis(
    zone_name: str = Query(..., description="区域名称"),
    start_time: datetime = Query(..., description="开始时间"),
    end_time: datetime = Query(..., description="结束时间"),
    threshold: float = Query(..., gt=0, description="波动阈值"),
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.name == zone_name).first()
    if not zone:
        return FluctuationAnalysisResponse(
            zone_name=zone_name,
            start_time=start_time,
            end_time=end_time,
            threshold=threshold,
            total=0,
            sensors=[],
        )

    sensor_ids = [s.sensor_id for s in db.query(Sensor).filter(Sensor.zone_id == zone.id).all()]
    if not sensor_ids:
        return FluctuationAnalysisResponse(
            zone_name=zone_name,
            start_time=start_time,
            end_time=end_time,
            threshold=threshold,
            total=0,
            sensors=[],
        )

    sensor_stats = []
    for sensor_id in sensor_ids:
        data_list = (
            db.query(SensorData)
            .filter(
                SensorData.sensor_id == sensor_id,
                SensorData.timestamp >= start_time,
                SensorData.timestamp <= end_time,
            )
            .order_by(SensorData.timestamp)
            .all()
        )

        if len(data_list) < 2:
            continue

        fluctuation_count = 0
        max_temp_change = 0.0
        max_humidity_change = 0.0
        last_fluctuation_time = None

        for i in range(1, len(data_list)):
            prev = data_list[i - 1]
            curr = data_list[i]

            temp_change = abs(curr.temperature - prev.temperature)
            humidity_change = abs(curr.humidity - prev.humidity)

            if temp_change > threshold or humidity_change > threshold:
                fluctuation_count += 1
                if temp_change > max_temp_change:
                    max_temp_change = temp_change
                if humidity_change > max_humidity_change:
                    max_humidity_change = humidity_change
                last_fluctuation_time = curr.timestamp

        if fluctuation_count > 0:
            sensor_stats.append(
                FluctuationSensorItem(
                    sensor_id=sensor_id,
                    fluctuation_count=fluctuation_count,
                    max_temp_change=round(max_temp_change, 2),
                    max_humidity_change=round(max_humidity_change, 2),
                    last_fluctuation_time=last_fluctuation_time,
                )
            )

    sensor_stats.sort(
        key=lambda x: (-x.fluctuation_count, -x.last_fluctuation_time.timestamp() if x.last_fluctuation_time else 0)
    )

    return FluctuationAnalysisResponse(
        zone_name=zone_name,
        start_time=start_time,
        end_time=end_time,
        threshold=threshold,
        total=len(sensor_stats),
        sensors=sensor_stats,
    )


@router.get("/detail", response_model=FluctuationDetailResponse, summary="传感器异常波动明细")
def fluctuation_detail(
    zone_name: str = Query(..., description="区域名称"),
    sensor_id: str = Query(..., description="传感器编号"),
    start_time: datetime = Query(..., description="开始时间"),
    end_time: datetime = Query(..., description="结束时间"),
    threshold: float = Query(..., gt=0, description="波动阈值"),
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.name == zone_name).first()
    if not zone:
        return FluctuationDetailResponse(
            zone_name=zone_name,
            sensor_id=sensor_id,
            start_time=start_time,
            end_time=end_time,
            threshold=threshold,
            total=0,
            fluctuations=[],
        )

    sensor = (
        db.query(Sensor)
        .filter(Sensor.zone_id == zone.id, Sensor.sensor_id == sensor_id)
        .first()
    )
    if not sensor:
        return FluctuationDetailResponse(
            zone_name=zone_name,
            sensor_id=sensor_id,
            start_time=start_time,
            end_time=end_time,
            threshold=threshold,
            total=0,
            fluctuations=[],
        )

    data_list = (
        db.query(SensorData)
        .filter(
            SensorData.sensor_id == sensor_id,
            SensorData.timestamp >= start_time,
            SensorData.timestamp <= end_time,
        )
        .order_by(SensorData.timestamp)
        .all()
    )

    fluctuations = []
    if len(data_list) >= 2:
        for i in range(1, len(data_list)):
            prev = data_list[i - 1]
            curr = data_list[i]

            temp_change = abs(curr.temperature - prev.temperature)
            humidity_change = abs(curr.humidity - prev.humidity)

            if temp_change > threshold or humidity_change > threshold:
                fluctuations.append(
                    FluctuationDetailItem(
                        before=FluctuationDataPoint(
                            temperature=prev.temperature,
                            humidity=prev.humidity,
                            timestamp=prev.timestamp,
                        ),
                        after=FluctuationDataPoint(
                            temperature=curr.temperature,
                            humidity=curr.humidity,
                            timestamp=curr.timestamp,
                        ),
                        temp_change=round(temp_change, 2),
                        humidity_change=round(humidity_change, 2),
                    )
                )

    return FluctuationDetailResponse(
        zone_name=zone_name,
        sensor_id=sensor_id,
        start_time=start_time,
        end_time=end_time,
        threshold=threshold,
        total=len(fluctuations),
        fluctuations=fluctuations,
    )
