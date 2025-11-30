import { useState } from "react";
import { QueryClient, QueryClientProvider, useQuery, useMutation } from "@tanstack/react-query";
import { runBacktest, getRecentEarnings, validateResults, searchStockEarnings, getHistory, getHistoryDetail, deleteHistory, saveToHistory } from "./api";
import type { BacktestResult, BacktestRequest } from "./types";
import type { HistoryRecord, HistoryDetail } from "./api";
import "./App.css";

const queryClient = new QueryClient();

function formatMarketCap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(0)}`;
}

function ResultsTable({
  results,
  onValidate
}: {
  results: BacktestResult[];
  onValidate: (results: BacktestResult[]) => void;
}) {
  const validateMutation = useMutation({
    mutationFn: validateResults,
  });

  const handleValidate = () => {
    validateMutation.mutate(results);
    onValidate(results);
  };

  return (
    <div className="results-section">
      <div className="results-header">
        <h2>回測結果 ({results.length} 筆)</h2>
        <button
          onClick={handleValidate}
          disabled={validateMutation.isPending}
          className="validate-btn"
        >
          {validateMutation.isPending ? "驗證中..." : "🤖 AI 驗證"}
        </button>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>股票</th>
              <th>公司名稱</th>
              <th>市值</th>
              <th>Earnings日</th>
              <th>時間</th>
              <th>發佈前價格</th>
              <th>發佈後價格</th>
              <th>變動%</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={`${r.symbol}-${r.earnings_date}`}>
                <td className="symbol">{r.symbol}</td>
                <td>{r.company_name}</td>
                <td>{formatMarketCap(r.market_cap)}</td>
                <td>{r.earnings_date}</td>
                <td className={r.earnings_time === "BMO" ? "bmo" : r.earnings_time === "AMC" ? "amc" : ""}>
                  {r.earnings_time === "BMO" ? "盤前" : r.earnings_time === "AMC" ? "盤後" : "-"}
                </td>
                <td className="price">${r.price_before.toFixed(2)}<br/><span className="date-small">{r.date_before}</span></td>
                <td className="price">${r.price_after.toFixed(2)}<br/><span className="date-small">{r.date_after}</span></td>
                <td className={`price-change ${r.price_change_pct >= 0 ? "positive" : "negative"}`}>
                  {r.price_change_pct >= 0 ? "+" : ""}{(r.price_change_pct * 100).toFixed(2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function getDaysDiff(start: string, end: string): number {
  if (!start || !end) return 0;
  const startDate = new Date(start);
  const endDate = new Date(end);
  const diffTime = endDate.getTime() - startDate.getTime();
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

function HistoryModal({
  isOpen,
  onClose,
  onLoadHistory,
}: {
  isOpen: boolean;
  onClose: () => void;
  onLoadHistory: (results: BacktestResult[]) => void;
}) {
  const [selectedRecord, setSelectedRecord] = useState<HistoryRecord | null>(null);
  const [historyDetail, setHistoryDetail] = useState<HistoryDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const historyQuery = useQuery({
    queryKey: ["history"],
    queryFn: () => getHistory("", 50),
    enabled: isOpen,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteHistory,
    onSuccess: () => {
      historyQuery.refetch();
      setSelectedRecord(null);
      setHistoryDetail(null);
    },
  });

  const handleSelectRecord = async (record: HistoryRecord) => {
    setSelectedRecord(record);
    setIsLoadingDetail(true);
    try {
      const detail = await getHistoryDetail(record.object_name);
      setHistoryDetail(detail);
    } catch (e) {
      console.error("Failed to load detail:", e);
    }
    setIsLoadingDetail(false);
  };

  const handleLoadResults = () => {
    if (historyDetail?.results) {
      onLoadHistory(historyDetail.results);
      onClose();
    }
  };

  const formatQueryType = (type: string) => {
    switch (type) {
      case "stock": return "單一股票";
      case "recent": return "最近 Earnings";
      case "custom": return "自訂日期";
      default: return type;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>歷史查詢記錄</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="history-container">
          <div className="history-list">
            {historyQuery.isLoading && <div className="loading">載入中...</div>}
            {historyQuery.error && <div className="error">載入失敗</div>}
            {historyQuery.data?.length === 0 && <div className="no-data">尚無歷史記錄</div>}
            {historyQuery.data?.map((record) => (
              <div
                key={record.object_name}
                className={`history-item ${selectedRecord?.object_name === record.object_name ? "selected" : ""}`}
                onClick={() => handleSelectRecord(record)}
              >
                <div className="history-item-type">{formatQueryType(record.query_type)}</div>
                <div className="history-item-key">{record.query_key || "-"}</div>
                <div className="history-item-time">
                  {new Date(record.last_modified).toLocaleString("zh-TW")}
                </div>
              </div>
            ))}
          </div>

          <div className="history-detail">
            {!selectedRecord && <div className="no-data">選擇一筆記錄查看詳情</div>}
            {isLoadingDetail && <div className="loading">載入詳情中...</div>}
            {selectedRecord && historyDetail && !isLoadingDetail && (
              <>
                <div className="detail-info">
                  <p><strong>類型：</strong>{formatQueryType(historyDetail.query_type)}</p>
                  <p><strong>時間：</strong>{new Date(historyDetail.timestamp).toLocaleString("zh-TW")}</p>
                  <p><strong>結果數：</strong>{historyDetail.count} 筆</p>
                  {historyDetail.params && Object.keys(historyDetail.params).length > 0 && (
                    <p><strong>參數：</strong>{JSON.stringify(historyDetail.params)}</p>
                  )}
                </div>
                <div className="detail-actions">
                  <button
                    className="load-btn"
                    onClick={handleLoadResults}
                    disabled={!historyDetail.results?.length}
                  >
                    載入結果
                  </button>
                  <button
                    className="delete-btn"
                    onClick={() => deleteMutation.mutate(selectedRecord.object_name)}
                    disabled={deleteMutation.isPending}
                  >
                    {deleteMutation.isPending ? "刪除中..." : "刪除"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Dashboard() {
  const [mode, setMode] = useState<"recent" | "custom" | "stock" | "batch">("stock");
  const [days, setDays] = useState(7);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [minMarketCap, setMinMarketCap] = useState(1);
  const [hasSearched, setHasSearched] = useState(false);
  const [stockSymbol, setStockSymbol] = useState("");
  const [stockStartDate, setStockStartDate] = useState("2025-01-01");
  const [stockEndDate, setStockEndDate] = useState(new Date().toISOString().split('T')[0]);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [loadedResults, setLoadedResults] = useState<BacktestResult[] | null>(null);
  // 批次查詢
  const [batchSymbols, setBatchSymbols] = useState("");
  const [batchStartDate, setBatchStartDate] = useState("2025-01-01");
  const [batchEndDate, setBatchEndDate] = useState(new Date().toISOString().split('T')[0]);
  const [batchResults, setBatchResults] = useState<BacktestResult[]>([]);
  const [batchProgress, setBatchProgress] = useState({ current: 0, total: 0, currentSymbol: "" });
  const [isBatchLoading, setIsBatchLoading] = useState(false);

  const saveMutation = useMutation({
    mutationFn: ({ queryType, results, params }: { queryType: string; results: BacktestResult[]; params: Record<string, unknown> }) =>
      saveToHistory(queryType, results, params),
  });

  // 計算自訂日期範圍是否超過 30 天
  const customDateDiff = getDaysDiff(startDate, endDate);
  const isCustomDateRangeInvalid = customDateDiff > 30 || customDateDiff < 0;

  const recentQuery = useQuery({
    queryKey: ["recent", days, minMarketCap],
    queryFn: () => getRecentEarnings(days, minMarketCap * 1e9),
    enabled: mode === "recent" && hasSearched,
  });

  const customMutation = useMutation({
    mutationFn: (request: BacktestRequest) => runBacktest(request),
  });

  const stockMutation = useMutation({
    mutationFn: ({ symbol, startDate, endDate }: { symbol: string; startDate: string; endDate: string }) =>
      searchStockEarnings(symbol, startDate, endDate),
  });

  // 解析批次輸入的股票代號
  const parseSymbols = (input: string): string[] => {
    return input
      .toUpperCase()
      .split(/[\s,;，；]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0 && /^[A-Z]+$/.test(s));
  };

  // 批次查詢
  const handleBatchSearch = async () => {
    const symbols = parseSymbols(batchSymbols);
    if (symbols.length === 0 || !batchStartDate || !batchEndDate) return;

    setIsBatchLoading(true);
    setBatchResults([]);
    setBatchProgress({ current: 0, total: symbols.length, currentSymbol: "" });

    const allResults: BacktestResult[] = [];

    for (let i = 0; i < symbols.length; i++) {
      const symbol = symbols[i];
      setBatchProgress({ current: i + 1, total: symbols.length, currentSymbol: symbol });

      try {
        const results = await searchStockEarnings(symbol, batchStartDate, batchEndDate);
        allResults.push(...results);
      } catch (e) {
        console.error(`Failed to fetch ${symbol}:`, e);
      }
    }

    setBatchResults(allResults);
    setIsBatchLoading(false);
  };

  const handleSearch = () => {
    if (mode === "recent") {
      setHasSearched(true);
      recentQuery.refetch();
    } else if (mode === "custom") {
      if (!startDate || !endDate) return;
      customMutation.mutate({
        start_date: startDate,
        end_date: endDate,
        min_market_cap: minMarketCap * 1e9,
      });
    } else if (mode === "stock") {
      if (!stockSymbol || !stockStartDate || !stockEndDate) return;
      stockMutation.mutate({
        symbol: stockSymbol.toUpperCase(),
        startDate: stockStartDate,
        endDate: stockEndDate,
      });
    } else if (mode === "batch") {
      handleBatchSearch();
    }
  };

  const results = loadedResults ?? (mode === "recent"
    ? recentQuery.data
    : mode === "custom"
      ? customMutation.data
      : mode === "batch"
        ? batchResults
        : stockMutation.data);
  const isLoading = mode === "recent"
    ? recentQuery.isLoading || recentQuery.isFetching
    : mode === "custom"
      ? customMutation.isPending
      : mode === "batch"
        ? isBatchLoading
        : stockMutation.isPending;
  const error = mode === "recent"
    ? recentQuery.error
    : mode === "custom"
      ? customMutation.error
      : mode === "batch"
        ? null
        : stockMutation.error;
  const showResults = loadedResults !== null || (mode === "recent"
    ? hasSearched
    : mode === "custom"
      ? customMutation.data !== undefined
      : mode === "batch"
        ? batchResults.length > 0 || isBatchLoading
        : stockMutation.data !== undefined);

  const handleSaveResults = () => {
    if (!results || results.length === 0) return;
    const params: Record<string, unknown> = {};
    if (mode === "stock") {
      params.symbol = stockSymbol;
      params.start_date = stockStartDate;
      params.end_date = stockEndDate;
    } else if (mode === "recent") {
      params.days = days;
      params.min_market_cap = minMarketCap * 1e9;
    } else {
      params.start_date = startDate;
      params.end_date = endDate;
      params.min_market_cap = minMarketCap * 1e9;
    }
    saveMutation.mutate({ queryType: mode, results, params });
  };

  const handleLoadHistory = (historyResults: BacktestResult[]) => {
    setLoadedResults(historyResults);
  };

  return (
    <div className="dashboard">
      <header>
        <h1>📈 Earnings Call Backtest</h1>
        <p>找出 Earnings Call 發佈後價格變動超過 10% 的股票</p>
        <button
          className="history-btn"
          onClick={() => setShowHistoryModal(true)}
        >
          查看歷史記錄
        </button>
      </header>

      <div className="controls">
        <div className="mode-toggle">
          <button
            className={mode === "stock" ? "active" : ""}
            onClick={() => setMode("stock")}
          >
            單一股票查詢
          </button>
          <button
            className={mode === "recent" ? "active" : ""}
            onClick={() => setMode("recent")}
          >
            最近 Earnings
          </button>
          <button
            className={mode === "custom" ? "active" : ""}
            onClick={() => setMode("custom")}
          >
            自訂日期
          </button>
          <button
            className={mode === "batch" ? "active" : ""}
            onClick={() => setMode("batch")}
          >
            批次查詢
          </button>
        </div>

        <div className="filters">
          {mode === "recent" ? (
            <div className="filter-group">
              <label>過去天數</label>
              <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
                <option value={7}>7 天</option>
                <option value={14}>14 天</option>
                <option value={30}>30 天</option>
              </select>
            </div>
          ) : mode === "custom" ? (
            <>
              <div className="filter-group">
                <label>開始日期</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>結束日期</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
                {isCustomDateRangeInvalid && startDate && endDate && (
                  <span className="date-error">
                    {customDateDiff < 0 ? "結束日期需晚於開始日期" : "日期範圍最多 30 天"}
                  </span>
                )}
              </div>
            </>
          ) : mode === "batch" ? (
            <>
              <div className="filter-group" style={{ flex: 2 }}>
                <label>股票代碼（用空格、逗號或分號分隔）</label>
                <input
                  type="text"
                  value={batchSymbols}
                  onChange={(e) => setBatchSymbols(e.target.value.toUpperCase())}
                  placeholder="如：AAPL MSFT NVDA, TSLA; GOOGL"
                  className="stock-input"
                  style={{ minWidth: "300px" }}
                />
                {batchSymbols && (
                  <span style={{ fontSize: "0.75rem", color: "#888" }}>
                    已輸入 {parseSymbols(batchSymbols).length} 個股票
                  </span>
                )}
              </div>
              <div className="filter-group">
                <label>開始日期</label>
                <input
                  type="date"
                  value={batchStartDate}
                  onChange={(e) => setBatchStartDate(e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>結束日期</label>
                <input
                  type="date"
                  value={batchEndDate}
                  onChange={(e) => setBatchEndDate(e.target.value)}
                />
              </div>
            </>
          ) : (
            <>
              <div className="filter-group">
                <label>股票代碼</label>
                <input
                  type="text"
                  value={stockSymbol}
                  onChange={(e) => setStockSymbol(e.target.value.toUpperCase())}
                  placeholder="如：AAPL"
                  className="stock-input"
                />
              </div>
              <div className="filter-group">
                <label>開始日期</label>
                <input
                  type="date"
                  value={stockStartDate}
                  onChange={(e) => setStockStartDate(e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>結束日期</label>
                <input
                  type="date"
                  value={stockEndDate}
                  onChange={(e) => setStockEndDate(e.target.value)}
                />
              </div>
            </>
          )}

          {mode !== "stock" && (
            <div className="filter-group">
              <label>最低市值 (B)</label>
              <input
                type="number"
                value={minMarketCap}
                onChange={(e) => setMinMarketCap(Number(e.target.value))}
                min={0}
                step={0.5}
              />
            </div>
          )}

          <button
            className="search-btn"
            onClick={handleSearch}
            disabled={
              isLoading ||
              (mode === "custom" && (!startDate || !endDate || isCustomDateRangeInvalid)) ||
              (mode === "stock" && (!stockSymbol || !stockStartDate || !stockEndDate)) ||
              (mode === "batch" && (parseSymbols(batchSymbols).length === 0 || !batchStartDate || !batchEndDate))
            }
          >
            {isLoading ? "搜尋中..." : "開始搜尋"}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="loading">
          <div className="spinner"></div>
          {mode === "batch" ? (
            <>
              <p>正在批次查詢股票...</p>
              <p style={{ fontWeight: 600, color: "#4f46e5" }}>
                {batchProgress.currentSymbol} ({batchProgress.current}/{batchProgress.total})
              </p>
              <div style={{ width: "200px", height: "8px", background: "#333", borderRadius: "4px", margin: "0.5rem auto" }}>
                <div
                  style={{
                    width: `${batchProgress.total > 0 ? (batchProgress.current / batchProgress.total) * 100 : 0}%`,
                    height: "100%",
                    background: "#4f46e5",
                    borderRadius: "4px",
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
            </>
          ) : (
            <>
              <p>正在搜尋符合條件的股票，請稍候...</p>
              <p className="loading-hint">這可能需要 30-60 秒</p>
            </>
          )}
        </div>
      )}
      {error && <div className="error">錯誤: {(error as Error).message}</div>}
      {!isLoading && showResults && results && results.length > 0 && (
        <>
          <ResultsTable results={results} onValidate={() => {}} />
          <div className="save-section">
            <button
              className="save-btn"
              onClick={handleSaveResults}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? "儲存中..." : saveMutation.isSuccess ? "已儲存" : "儲存結果到歷史記錄"}
            </button>
            {loadedResults && (
              <button
                className="clear-btn"
                onClick={() => setLoadedResults(null)}
              >
                清除載入的結果
              </button>
            )}
          </div>
        </>
      )}
      {!isLoading && showResults && results && results.length === 0 && (
        <div className="no-data">沒有符合條件的資料</div>
      )}
      {!isLoading && !showResults && (
        <div className="no-data">請設定條件後按「開始搜尋」</div>
      )}

      <HistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        onLoadHistory={handleLoadHistory}
      />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}

export default App;
