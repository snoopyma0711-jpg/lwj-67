from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SensorConfig(BaseModel):
    sensor_id: str = Field(..., description="传感器ID")


class ZoneConfig(BaseModel):
    name: str = Field(..., description="区域名称")
    temp_lower: float = Field(..., description="温度下限")
    temp_upper: float = Field(..., description="温度上限")
    humidity_lower: float = Field(..., description="湿度下限")
    humidity_upper: float = Field(..., description="湿度上限")
    sensor_ids: list[str] = Field(..., description="传感器ID列表")


class InitRequest(BaseModel):
    zones: list[ZoneConfig]


class SensorDataItem(BaseModel):
    sensor_id: str
    temperature: float
    humidity: float
    timestamp: datetime


class DataUploadRequest(BaseModel):
    data: list[SensorDataItem] = Field(..., max_length=200)


class DataUploadResponse(BaseModel):
    received: int
    duplicates: int


class MinuteDataPoint(BaseModel):
    minute: datetime
    avg_temperature: float
    avg_humidity: float


class HistoryQueryResponse(BaseModel):
    zone_name: str
    data: list[MinuteDataPoint]


class AlertItem(BaseModel):
    id: int
    zone_name: str
    sensor_id: str
    alert_type: str
    level: str
    started_at: datetime
    duration_seconds: int
    status: str
    resolved_note: Optional[str] = None


class AlertListResponse(BaseModel):
    total: int
    alerts: list[AlertItem]


class ResolveAlertRequest(BaseModel):
    resolved_note: str = Field(..., min_length=1)


class ZoneAlertStats(BaseModel):
    zone_name: str
    normal_count: int
    urgent_count: int
    avg_response_seconds: Optional[float] = None


class AlertStatsResponse(BaseModel):
    stats: list[ZoneAlertStats]


class SensorHealthItem(BaseModel):
    sensor_id: str
    status: str
    score: int
    report_count: int
    exceed_count: int
    last_report_time: Optional[datetime] = None


class SensorHealthDashboardResponse(BaseModel):
    zone_name: str
    sensors: list[SensorHealthItem]


class ExportDataItem(BaseModel):
    sensor_id: str
    temperature: float
    humidity: float
    timestamp: datetime
    is_exceeded: bool


class ExportListResponse(BaseModel):
    zone_name: str
    total: int
    data: list[ExportDataItem]


class FluctuationSensorItem(BaseModel):
    sensor_id: str
    fluctuation_count: int
    max_temp_change: float
    max_humidity_change: float
    last_fluctuation_time: datetime


class FluctuationAnalysisResponse(BaseModel):
    zone_name: str
    start_time: datetime
    end_time: datetime
    threshold: float
    total: int
    sensors: list[FluctuationSensorItem]


class FluctuationDataPoint(BaseModel):
    temperature: float
    humidity: float
    timestamp: datetime


class FluctuationDetailItem(BaseModel):
    before: FluctuationDataPoint
    after: FluctuationDataPoint
    temp_change: float
    humidity_change: float


class FluctuationDetailResponse(BaseModel):
    zone_name: str
    sensor_id: str
    start_time: datetime
    end_time: datetime
    threshold: float
    total: int
    fluctuations: list[FluctuationDetailItem]


class LongestAlertItem(BaseModel):
    id: int
    sensor_id: str
    alert_type: str
    level: str
    started_at: datetime
    duration_seconds: int


class MostFluctuationSensorItem(BaseModel):
    sensor_id: str
    fluctuation_count: int
    max_temp_change: float
    max_humidity_change: float


class ZoneDailyReportItem(BaseModel):
    zone_name: str
    reported_sensor_count: int
    actual_report_count: int
    missing_sensor_count: int
    alert_count: int
    longest_alert: Optional[LongestAlertItem] = None
    most_fluctuation_sensor: Optional[MostFluctuationSensorItem] = None
    earliest_report_time: Optional[datetime] = None
    latest_report_time: Optional[datetime] = None


class DailyReportOverview(BaseModel):
    total_report_count: int
    total_alert_count: int
    worst_missing_zone: Optional[str] = None
    worst_missing_count: int = 0


class DailyReportResponse(BaseModel):
    date: str
    overview: DailyReportOverview
    zones: list[ZoneDailyReportItem]


class MissingPeriodItem(BaseModel):
    start_time: datetime
    end_time: datetime
    duration_seconds: int


class MissingSensorDetail(BaseModel):
    sensor_id: str
    missing_periods: list[MissingPeriodItem]


class MissingDetailResponse(BaseModel):
    zone_name: str
    date: str
    total_missing_sensors: int
    sensors: list[MissingSensorDetail]
