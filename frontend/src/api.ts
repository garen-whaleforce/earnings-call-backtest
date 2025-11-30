import axios from "axios";
import type { BacktestResult, BacktestRequest, ValidationResult } from "./types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8010";

const api = axios.create({
  baseURL: API_BASE,
});

export async function runBacktest(
  request: BacktestRequest
): Promise<BacktestResult[]> {
  const response = await api.post<BacktestResult[]>("/api/backtest/run", request);
  return response.data;
}

export async function getRecentEarnings(
  days: number = 7,
  minMarketCap: number = 1_000_000_000
): Promise<BacktestResult[]> {
  const response = await api.get<BacktestResult[]>("/api/backtest/recent", {
    params: { days, min_market_cap: minMarketCap },
  });
  return response.data;
}

export async function getStockBacktest(
  symbol: string,
  earningsDate: string
): Promise<BacktestResult> {
  const response = await api.get<BacktestResult>(
    `/api/backtest/stock/${symbol}`,
    { params: { earnings_date: earningsDate } }
  );
  return response.data;
}

export async function validateResults(
  results: BacktestResult[]
): Promise<ValidationResult[]> {
  const response = await api.post<ValidationResult[]>(
    "/api/backtest/validate",
    results
  );
  return response.data;
}

export async function analyzePattern(
  results: BacktestResult[]
): Promise<Record<string, unknown>> {
  const response = await api.post("/api/backtest/analyze", results);
  return response.data;
}

export async function searchStockEarnings(
  symbol: string,
  startDate: string,
  endDate: string
): Promise<BacktestResult[]> {
  const response = await api.get<BacktestResult[]>(
    `/api/backtest/stock-search/${symbol}`,
    { params: { start_date: startDate, end_date: endDate } }
  );
  return response.data;
}

// ==================== 歷史記錄 API ====================

export interface HistoryRecord {
  object_name: string;
  query_type: string;
  query_key?: string;
  size: number;
  last_modified: string;
}

export interface HistoryDetail {
  query_type: string;
  params: Record<string, unknown>;
  results: BacktestResult[];
  timestamp: string;
  count: number;
}

export async function getHistory(
  prefix: string = "",
  limit: number = 50
): Promise<HistoryRecord[]> {
  const response = await api.get<HistoryRecord[]>("/api/backtest/history", {
    params: { prefix, limit },
  });
  return response.data;
}

export async function getHistoryDetail(
  objectName: string
): Promise<HistoryDetail> {
  const response = await api.get<HistoryDetail>(
    `/api/backtest/history/${objectName}`
  );
  return response.data;
}

export async function deleteHistory(objectName: string): Promise<void> {
  await api.delete(`/api/backtest/history/${objectName}`);
}

export async function saveToHistory(
  queryType: string,
  results: BacktestResult[],
  params: Record<string, unknown>
): Promise<{ object_name: string; message: string }> {
  const response = await api.post("/api/backtest/history/save", results, {
    params: { query_type: queryType },
    headers: { "Content-Type": "application/json" },
  });
  return response.data;
}
