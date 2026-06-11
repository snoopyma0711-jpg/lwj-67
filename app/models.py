from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, UniqueConstraint, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    temp_lower = Column(Float, nullable=False)
    temp_upper = Column(Float, nullable=False)
    humidity_lower = Column(Float, nullable=False)
    humidity_upper = Column(Float, nullable=False)

    sensors = relationship("Sensor", back_populates="zone", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="zone", cascade="all, delete-orphan")


class Sensor(Base):
    __tablename__ = "sensors"
    __table_args__ = (
        UniqueConstraint("sensor_id", name="uq_sensor_id"),
        Index("ix_sensor_zone_id", "zone_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(String(64), nullable=False)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    zone = relationship("Zone", back_populates="sensors")


class SensorData(Base):
    __tablename__ = "sensor_data"
    __table_args__ = (
        UniqueConstraint("sensor_id", "timestamp", name="uq_sensor_timestamp"),
        Index("ix_sensor_data_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(String(64), nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_zone_status", "zone_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    sensor_id = Column(String(64), nullable=False)
    alert_type = Column(String(32), nullable=False)
    started_at = Column(DateTime, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="unprocessed")
    resolved_note = Column(Text, nullable=True)

    zone = relationship("Zone", back_populates="alerts")


class ConsecutiveExceed(Base):
    __tablename__ = "consecutive_exceeds"
    __table_args__ = (
        UniqueConstraint("sensor_id", "exceed_type", name="uq_sensor_exceed_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(String(64), nullable=False)
    exceed_type = Column(String(32), nullable=False)
    count = Column(Integer, nullable=False, default=0)
    first_exceeded_at = Column(DateTime, nullable=True)
