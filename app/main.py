from fastapi import FastAPI
from app.database import engine, Base
from app.routers import init, data, query, alert, export, fluctuation, daily_report

Base.metadata.create_all(bind=engine)

app = FastAPI(title="仓库货架温湿度监控系统", version="1.0.0")

app.include_router(init.router)
app.include_router(data.router)
app.include_router(query.router)
app.include_router(alert.router)
app.include_router(export.router)
app.include_router(fluctuation.router)
app.include_router(daily_report.router)


@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}
