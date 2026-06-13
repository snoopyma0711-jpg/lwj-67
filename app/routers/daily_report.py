from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Zone, Sensor, SensorData, Alert
from app.schemas import (
    DailyReportResponse,
    DailyReportOverview,
    ZoneDailyReportItem,
    LongestAlertItem,
    MostFluctuationSensorItem,
    MissingDetailResponse,
    MissingSensorDetail,
    MissingPeriodItem,
)

router = APIRouter(prefix="/api/daily-report", tags=["区域巡检日报"])

GAP_THRESHOLD_SECONDS = 300
FLUCTUATION_THRESHOLD = 5.0


def _parse_date_range(date_str: str):
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    day_start = datetime(day.year, day.month, day.day, 0, 0, 0)
    day_end = datetime(day.year, day.month, day.day, 23, 59, 59)
    return day_start, day_end


def _find_longest_alert(db: Session, zone_id: int, day_start: datetime, day_end: datetime):
    alert = (
        db.query(Alert)
        .filter(
            Alert.zone_id == zone_id,
            Alert.started_at >= day_start,
            Alert.started_at <= day_end,
        )
        .order_by(Alert.duration_seconds.desc())
        .first()
    )
    if not alert:
        return None
    return LongestAlertItem(
        id=alert.id,
        sensor_id=alert.sensor_id,
        alert_type=alert.alert_type,
        level=alert.level,
        started_at=alert.started_at,
        duration_seconds=alert.duration_seconds,
    )


def _find_most_fluctuation_sensor(
    db: Session, sensor_ids: list[str], day_start: datetime, day_end: datetime
):
    best = None
    for sensor_id in sensor_ids:
        data_list = (
            db.query(SensorData)
            .filter(
                SensorData.sensor_id == sensor_id,
                SensorData.timestamp >= day_start,
                SensorData.timestamp <= day_end,
            )
            .order_by(SensorData.timestamp)
            .all()
        )
        if len(data_list) < 2:
            continue

        fluctuation_count = 0
        max_temp_change = 0.0
        max_humidity_change = 0.0

        for i in range(1, len(data_list)):
            prev = data_list[i - 1]
            curr = data_list[i]
            temp_change = abs(curr.temperature - prev.temperature)
            humidity_change = abs(curr.humidity - prev.humidity)

            if temp_change > FLUCTUATION_THRESHOLD or humidity_change > FLUCTUATION_THRESHOLD:
                fluctuation_count += 1
                if temp_change > max_temp_change:
                    max_temp_change = temp_change
                if humidity_change > max_humidity_change:
                    max_humidity_change = humidity_change

        if fluctuation_count > 0:
            if best is None or fluctuation_count > best.fluctuation_count:
                best = MostFluctuationSensorItem(
                    sensor_id=sensor_id,
                    fluctuation_count=fluctuation_count,
                    max_temp_change=round(max_temp_change, 2),
                    max_humidity_change=round(max_humidity_change, 2),
                )

    return best


def _find_missing_periods(
    data_list: list[SensorData], day_start: datetime, day_end: datetime
) -> list[MissingPeriodItem]:
    if not data_list:
        return [MissingPeriodItem(
            start_time=day_start,
            end_time=day_end,
            duration_seconds=int((day_end - day_start).total_seconds()),
        )]

    periods = []

    if (data_list[0].timestamp - day_start).total_seconds() > GAP_THRESHOLD_SECONDS:
        periods.append(MissingPeriodItem(
            start_time=day_start,
            end_time=data_list[0].timestamp,
            duration_seconds=int((data_list[0].timestamp - day_start).total_seconds()),
        ))

    for i in range(1, len(data_list)):
        prev = data_list[i - 1]
        curr = data_list[i]
        gap = (curr.timestamp - prev.timestamp).total_seconds()
        if gap > GAP_THRESHOLD_SECONDS:
            periods.append(MissingPeriodItem(
                start_time=prev.timestamp,
                end_time=curr.timestamp,
                duration_seconds=int(gap),
            ))

    if (day_end - data_list[-1].timestamp).total_seconds() > GAP_THRESHOLD_SECONDS:
        periods.append(MissingPeriodItem(
            start_time=data_list[-1].timestamp,
            end_time=day_end,
            duration_seconds=int((day_end - data_list[-1].timestamp).total_seconds()),
        ))

    return periods


def _has_missing_reports(data_list: list[SensorData], day_start: datetime, day_end: datetime) -> bool:
    if not data_list:
        return True
    if (data_list[0].timestamp - day_start).total_seconds() > GAP_THRESHOLD_SECONDS:
        return True
    for i in range(1, len(data_list)):
        gap = (data_list[i].timestamp - data_list[i - 1].timestamp).total_seconds()
        if gap > GAP_THRESHOLD_SECONDS:
            return True
    if (day_end - data_list[-1].timestamp).total_seconds() > GAP_THRESHOLD_SECONDS:
        return True
    return False


@router.get("", response_model=DailyReportResponse, summary="区域巡检日报")
def daily_report(
    date: str = Query(..., description="日期，格式 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    day_start, day_end = _parse_date_range(date)

    zones = db.query(Zone).all()
    zone_reports = []
    total_report_count = 0
    total_alert_count = 0
    worst_missing_zone = None
    worst_missing_count = -1

    for zone in zones:
        sensors = db.query(Sensor).filter(Sensor.zone_id == zone.id).all()
        sensor_ids = [s.sensor_id for s in sensors]
        total_sensors = len(sensor_ids)

        if total_sensors == 0:
            zone_reports.append(ZoneDailyReportItem(
                zone_name=zone.name,
                reported_sensor_count=0,
                actual_report_count=0,
                missing_sensor_count=0,
                alert_count=0,
            ))
            continue

        reported_ids = set()
        actual_count = 0
        earliest = None
        latest = None
        sensor_data_map: dict[str, list[SensorData]] = {sid: [] for sid in sensor_ids}

        rows = (
            db.query(SensorData)
            .filter(
                SensorData.sensor_id.in_(sensor_ids),
                SensorData.timestamp >= day_start,
                SensorData.timestamp <= day_end,
            )
            .order_by(SensorData.timestamp)
            .all()
        )

        for row in rows:
            reported_ids.add(row.sensor_id)
            actual_count += 1
            sensor_data_map[row.sensor_id].append(row)
            if earliest is None or row.timestamp < earliest:
                earliest = row.timestamp
            if latest is None or row.timestamp > latest:
                latest = row.timestamp

        reported_sensor_count = len(reported_ids)

        missing_sensor_count = 0
        for sid in sensor_ids:
            if _has_missing_reports(sensor_data_map[sid], day_start, day_end):
                missing_sensor_count += 1

        alert_count = db.query(Alert).filter(
            Alert.zone_id == zone.id,
            Alert.started_at >= day_start,
            Alert.started_at <= day_end,
        ).count()

        longest_alert = _find_longest_alert(db, zone.id, day_start, day_end)
        most_fluctuation = _find_most_fluctuation_sensor(db, sensor_ids, day_start, day_end)

        zone_reports.append(ZoneDailyReportItem(
            zone_name=zone.name,
            reported_sensor_count=reported_sensor_count,
            actual_report_count=actual_count,
            missing_sensor_count=missing_sensor_count,
            alert_count=alert_count,
            longest_alert=longest_alert,
            most_fluctuation_sensor=most_fluctuation,
            earliest_report_time=earliest,
            latest_report_time=latest,
        ))

        total_report_count += actual_count
        total_alert_count += alert_count

        if missing_sensor_count > worst_missing_count:
            worst_missing_count = missing_sensor_count
            worst_missing_zone = zone.name

    overview = DailyReportOverview(
        total_report_count=total_report_count,
        total_alert_count=total_alert_count,
        worst_missing_zone=worst_missing_zone if worst_missing_count > 0 else None,
        worst_missing_count=worst_missing_count if worst_missing_count > 0 else 0,
    )

    return DailyReportResponse(date=date, overview=overview, zones=zone_reports)


@router.get("/missing-detail", response_model=MissingDetailResponse, summary="区域缺报传感器明细")
def missing_detail(
    date: str = Query(..., description="日期，格式 YYYY-MM-DD"),
    zone_name: str = Query(..., description="区域名称"),
    db: Session = Depends(get_db),
):
    day_start, day_end = _parse_date_range(date)

    zone = db.query(Zone).filter(Zone.name == zone_name).first()
    if not zone:
        return MissingDetailResponse(
            zone_name=zone_name,
            date=date,
            total_missing_sensors=0,
            sensors=[],
        )

    sensors = db.query(Sensor).filter(Sensor.zone_id == zone.id).all()
    if not sensors:
        return MissingDetailResponse(
            zone_name=zone_name,
            date=date,
            total_missing_sensors=0,
            sensors=[],
        )

    missing_sensors = []

    for sensor in sensors:
        sensor_id = sensor.sensor_id
        data_list = (
            db.query(SensorData)
            .filter(
                SensorData.sensor_id == sensor_id,
                SensorData.timestamp >= day_start,
                SensorData.timestamp <= day_end,
            )
            .order_by(SensorData.timestamp)
            .all()
        )

        periods = _find_missing_periods(data_list, day_start, day_end)
        if periods:
            missing_sensors.append(MissingSensorDetail(
                sensor_id=sensor_id,
                missing_periods=periods,
            ))

    return MissingDetailResponse(
        zone_name=zone_name,
        date=date,
        total_missing_sensors=len(missing_sensors),
        sensors=missing_sensors,
    )
