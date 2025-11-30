from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from datetime import date, timedelta
from ..services import BacktestService, OpenAIService
from ..services.minio_service import MinioService
from ..models import BacktestRequest, BacktestResult, ValidationResult

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("/run", response_model=List[BacktestResult])
async def run_backtest(request: BacktestRequest):
    """
    執行 Earnings Call 回測
    - 取得指定日期範圍的 earnings events
    - 篩選市值 > min_market_cap 的公司
    - 計算每個股票的 ±10% 價格區間
    """
    service = BacktestService()
    results = await service.run_backtest(request)
    return results


@router.get("/stock/{symbol}", response_model=BacktestResult)
async def get_stock_backtest(
    symbol: str,
    earnings_date: date = Query(..., description="Earnings 發佈日期"),
):
    """取得單一股票的回測結果"""
    service = BacktestService()
    result = await service.get_single_stock_backtest(symbol, earnings_date)

    if not result:
        raise HTTPException(status_code=404, detail=f"找不到 {symbol} 的資料")

    return result


@router.post("/validate", response_model=List[ValidationResult])
async def validate_results(results: List[BacktestResult]):
    """使用 Azure OpenAI 驗證回測結果的正確性"""
    service = OpenAIService()
    validations = await service.batch_validate(results)
    return validations


@router.post("/analyze")
async def analyze_pattern(results: List[BacktestResult]):
    """使用 Azure OpenAI 分析 earnings 模式"""
    service = OpenAIService()
    analysis = await service.analyze_earnings_pattern(results)
    return analysis


@router.get("/recent", response_model=List[BacktestResult])
async def get_recent_earnings(
    days: int = Query(default=7, ge=1, le=30, description="查詢過去幾天"),
    min_market_cap: float = Query(default=1_000_000_000, description="最低市值"),
):
    """取得最近幾天的 earnings 回測結果"""
    service = BacktestService()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    request = BacktestRequest(
        start_date=start_date,
        end_date=end_date,
        min_market_cap=min_market_cap,
    )

    results = await service.run_backtest(request)
    return results


@router.get("/stock-search/{symbol}", response_model=List[BacktestResult])
async def search_stock_earnings(
    symbol: str,
    start_date: date = Query(..., description="開始日期"),
    end_date: date = Query(..., description="結束日期"),
):
    """
    查詢單一股票在指定時間範圍內的所有 earnings call 資料
    返回：earnings call 時間（盤前/盤後）、發佈前股價、發佈後股價、漲跌幅
    查詢完成後自動儲存到歷史記錄
    """
    service = BacktestService()
    results = await service.search_stock_earnings(symbol.upper(), start_date, end_date)

    # 自動儲存到歷史記錄
    if results:
        try:
            minio_service = MinioService()
            params = {
                "symbol": symbol.upper(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            results_dict = [r.model_dump() for r in results]
            minio_service.save_query_result("stock", params, results_dict)
        except Exception:
            # 儲存失敗不影響正常回傳
            pass

    return results


# ==================== 歷史記錄 API ====================

@router.get("/history")
async def get_history(
    prefix: str = Query(default="", description="篩選前綴 (stock/, recent/, custom/)"),
    limit: int = Query(default=50, ge=1, le=200, description="最多返回筆數"),
):
    """取得歷史查詢記錄列表"""
    try:
        minio_service = MinioService()
        history = minio_service.list_history(prefix=prefix, limit=limit)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法取得歷史記錄: {str(e)}")


@router.get("/history/{object_name:path}")
async def get_history_detail(object_name: str):
    """取得特定歷史記錄的詳細資料"""
    try:
        minio_service = MinioService()
        detail = minio_service.get_history_detail(object_name)
        if not detail:
            raise HTTPException(status_code=404, detail="找不到該記錄")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法取得記錄詳情: {str(e)}")


@router.delete("/history/{object_name:path}")
async def delete_history(object_name: str):
    """刪除特定歷史記錄"""
    try:
        minio_service = MinioService()
        success = minio_service.delete_history(object_name)
        if not success:
            raise HTTPException(status_code=500, detail="刪除失敗")
        return {"message": "刪除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除失敗: {str(e)}")


@router.post("/history/save")
async def save_to_history(
    query_type: str = Query(..., description="查詢類型 (stock, recent, custom)"),
    results: List[BacktestResult] = [],
    params: Dict[str, Any] = {},
):
    """手動儲存查詢結果到歷史記錄"""
    try:
        minio_service = MinioService()
        results_dict = [r.model_dump() for r in results]
        object_name = minio_service.save_query_result(query_type, params, results_dict)
        if not object_name:
            raise HTTPException(status_code=500, detail="儲存失敗")
        return {"object_name": object_name, "message": "儲存成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"儲存失敗: {str(e)}")
