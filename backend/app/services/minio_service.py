import json
import io
from datetime import datetime
from typing import List, Dict, Optional, Any
from minio import Minio
from minio.error import S3Error
from ..config import get_settings


class MinioService:
    def __init__(self):
        settings = get_settings()
        self.endpoint = settings.minio_endpoint
        self.client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket
        self._connected = False
        self._ensure_bucket()

    def _ensure_bucket(self):
        """確保 bucket 存在"""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            self._connected = True
        except S3Error as e:
            print(f"MinIO bucket error: {e}")
            self._connected = False
        except Exception as e:
            print(f"MinIO connection error to {self.endpoint}: {e}")
            self._connected = False

    def save_query_result(
        self,
        query_type: str,
        params: Dict[str, Any],
        results: List[Dict],
    ) -> Optional[str]:
        """
        儲存查詢結果到 MinIO

        Args:
            query_type: 查詢類型 (stock, recent, custom)
            params: 查詢參數
            results: 查詢結果

        Returns:
            object_name: 儲存的檔案名稱
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 根據查詢類型產生檔名
        if query_type == "stock":
            symbol = params.get("symbol", "unknown")
            object_name = f"stock/{symbol}/{timestamp}.json"
        elif query_type == "recent":
            days = params.get("days", 0)
            object_name = f"recent/{days}d/{timestamp}.json"
        else:
            start = params.get("start_date", "")
            end = params.get("end_date", "")
            object_name = f"custom/{start}_{end}/{timestamp}.json"

        # 準備資料
        data = {
            "query_type": query_type,
            "params": params,
            "results": results,
            "timestamp": datetime.now().isoformat(),
            "count": len(results),
        }

        try:
            json_data = json.dumps(data, ensure_ascii=False, default=str)
            data_bytes = json_data.encode("utf-8")

            self.client.put_object(
                self.bucket,
                object_name,
                io.BytesIO(data_bytes),
                len(data_bytes),
                content_type="application/json",
            )
            return object_name
        except S3Error as e:
            print(f"MinIO save error: {e}")
            return None

    def list_history(self, prefix: str = "", limit: int = 50) -> List[Dict]:
        """
        列出歷史查詢記錄

        Args:
            prefix: 篩選前綴 (stock/, recent/, custom/)
            limit: 最多返回筆數

        Returns:
            歷史記錄列表
        """
        history = []
        try:
            objects = self.client.list_objects(
                self.bucket,
                prefix=prefix,
                recursive=True,
            )

            items = []
            for obj in objects:
                items.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                })

            # 按時間倒序排列
            items.sort(key=lambda x: x["last_modified"], reverse=True)

            # 取前 limit 筆
            for item in items[:limit]:
                # 解析檔名取得基本資訊
                name = item["name"]
                parts = name.split("/")

                record = {
                    "object_name": name,
                    "query_type": parts[0] if parts else "unknown",
                    "size": item["size"],
                    "last_modified": item["last_modified"].isoformat(),
                }

                # 嘗試取得更多資訊
                if len(parts) >= 2:
                    record["query_key"] = parts[1]

                history.append(record)

        except S3Error as e:
            print(f"MinIO list error: {e}")

        return history

    def get_history_detail(self, object_name: str) -> Optional[Dict]:
        """
        取得特定歷史記錄的詳細資料

        Args:
            object_name: 檔案名稱

        Returns:
            查詢記錄詳情
        """
        try:
            response = self.client.get_object(self.bucket, object_name)
            data = json.loads(response.read().decode("utf-8"))
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            print(f"MinIO get error: {e}")
            return None

    def delete_history(self, object_name: str) -> bool:
        """刪除特定歷史記錄"""
        try:
            self.client.remove_object(self.bucket, object_name)
            return True
        except S3Error as e:
            print(f"MinIO delete error: {e}")
            return False
