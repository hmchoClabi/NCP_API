"""Global CDN and legacy CDN+ inventory API wrappers."""

from typing import Dict, Optional

from ncp_api.base import BaseNCPAPI


class CdnAPI(BaseNCPAPI):
    """Expose read-only CDN instance-list APIs."""

    ENDPOINT_KEY = "cdn"

    def _get_instance_list(
        self,
        path: str,
        *,
        cdn_instance_no: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        if page_no is not None and page_size is None:
            raise ValueError("page_no를 지정할 때는 page_size도 지정해야 합니다.")

        params = {"responseFormatType": response_format_type}
        if cdn_instance_no is not None:
            params["cdnInstanceNo"] = cdn_instance_no
        if page_no is not None:
            params["pageNo"] = page_no
        if page_size is not None:
            params["pageSize"] = page_size

        return self.client.get(path, params=params)

    def get_global_cdn_instance_list(
        self,
        cdn_instance_no: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        return self._get_instance_list(
            "/getGlobalCdnInstanceList",
            cdn_instance_no=cdn_instance_no,
            page_no=page_no,
            page_size=page_size,
            response_format_type=response_format_type,
        )

    def get_cdn_plus_instance_list(
        self,
        cdn_instance_no: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        response_format_type: str = "json",
    ) -> Dict:
        return self._get_instance_list(
            "/getCdnPlusInstanceList",
            cdn_instance_no=cdn_instance_no,
            page_no=page_no,
            page_size=page_size,
            response_format_type=response_format_type,
        )
