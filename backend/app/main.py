from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import backtest_router

app = FastAPI(
    title="Earnings Call Backtest API",
    description="回測 Earnings Call 發佈後的股價變動",
    version="1.0.0",
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生產環境應該限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊 routers
app.include_router(backtest_router)


@app.get("/")
async def root():
    return {
        "message": "Earnings Call Backtest API",
        "docs": "/docs",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
