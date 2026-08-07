"""Cloud DB VPC inventory API wrappers."""

from typing import Dict, Optional

from ncp_api.base import BaseNCPAPI


class CloudDbAPI(BaseNCPAPI):
    """Expose read-only instance-list APIs for supported Cloud DB engines."""

    ENDPOINT_KEY = "clouddb"

    def _get_instance_list(
        self,
        path: str,
        *,
        region_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        if page_no is not None and page_size is None:
            raise ValueError("page_no를 지정할 때는 page_size도 지정해야 합니다.")

        params = {"responseFormatType": response_format_type}
        if region_code is not None:
            params["regionCode"] = region_code
        if page_no is not None:
            params["pageNo"] = page_no
        if page_size is not None:
            params["pageSize"] = page_size

        return self.client.get(path, params=params)

    def get_cloud_mysql_instance_list(
        self,
        region_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        return self._get_instance_list(
            "/vmysql/v2/getCloudMysqlInstanceList",
            region_code=region_code,
            page_no=page_no,
            page_size=page_size,
            response_format_type=response_format_type,
        )

    def get_cloud_postgresql_instance_list(
        self,
        region_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        return self._get_instance_list(
            "/vpostgresql/v2/getCloudPostgresqlInstanceList",
            region_code=region_code,
            page_no=page_no,
            page_size=page_size,
            response_format_type=response_format_type,
        )

    def get_cloud_mssql_instance_list(
        self,
        region_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        return self._get_instance_list(
            "/vmssql/v2/getCloudMssqlInstanceList",
            region_code=region_code,
            page_no=page_no,
            page_size=page_size,
            response_format_type=response_format_type,
        )

    def get_cloud_mongodb_instance_list(
        self,
        region_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        return self._get_instance_list(
            "/vmongodb/v2/getCloudMongoDbInstanceList",
            region_code=region_code,
            page_no=page_no,
            page_size=page_size,
            response_format_type=response_format_type,
        )

    def get_cloud_cache_instance_list(
        self,
        region_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        return self._get_instance_list(
            "/vcache/v2/getCloudCacheInstanceList",
            region_code=region_code,
            page_no=page_no,
            page_size=page_size,
            response_format_type=response_format_type,
        )
