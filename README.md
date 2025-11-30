# Earnings Call Backtest

追蹤 Earnings Call 發佈後的股價變動，計算 ±10% 價格區間，篩選市值 > 1B 的公司。

## 功能

- 📊 查詢指定日期範圍的 Earnings Calendar
- 💰 自動篩選市值 > 1B 的公司
- 📈 取得 Earnings 發佈後最近交易日的收盤價
- 🎯 計算 ±10% 價格區間
- 🤖 使用 Azure OpenAI 驗證計算結果

## 技術架構

### 後端 (Python FastAPI)
- FastAPI + Uvicorn
- FMP API 整合
- Azure OpenAI 整合

### 前端 (React + Vite)
- React 18 + TypeScript
- TanStack Query (資料獲取)
- Axios (HTTP 請求)

## 本地開發

### 環境需求
- Python 3.11+
- Node.js 18+

### 後端設置

```bash
cd backend

# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安裝依賴
pip install -r requirements.txt

# 設定環境變數
cp .env.example .env
# 編輯 .env 填入 API keys

# 啟動開發伺服器
uvicorn app.main:app --reload
```

### 前端設置

```bash
cd frontend

# 安裝依賴
npm install

# 設定環境變數
cp .env.example .env

# 啟動開發伺服器
npm run dev
```

## API Endpoints

| Method | Endpoint | 說明 |
|--------|----------|------|
| POST | `/api/backtest/run` | 執行回測 |
| GET | `/api/backtest/recent` | 取得最近 earnings |
| GET | `/api/backtest/stock/{symbol}` | 取得單一股票回測 |
| POST | `/api/backtest/validate` | AI 驗證結果 |
| POST | `/api/backtest/analyze` | AI 分析模式 |

## 部署到 Zeabur

1. 在 GitHub 建立 repository
2. 推送程式碼到 GitHub
3. 在 Zeabur 連結 GitHub repo
4. 設定環境變數：
   - `FMP_API_KEY`
   - `AZURE_OPENAI_API_KEY`
   - `AZURE_OPENAI_ENDPOINT`
   - `AZURE_OPENAI_DEPLOYMENT_NAME`
   - `VITE_API_URL` (設定為後端的 URL)

## 環境變數

### 後端
```
FMP_API_KEY=your_fmp_api_key
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

### 前端
```
VITE_API_URL=http://localhost:8000
```

## License

MIT
