"""Read-only Classic NAS inventory API."""

from typing import Dict, List, Optional

from ncp_api.base import BaseNCPAPI


class ClassicNasAPI(BaseNCPAPI):
    """Expose the minimal Classic NAS API used by report inventory."""

    ENDPOINT_KEY = "nas_classic"

    def get_nas_volume_instance_list(
        self,
        volume_allotment_protocol_type_code: Optional[str] = None,
        is_event_configuration: Optional[bool] = None,
        is_snapshot_configuration: Optional[bool] = None,
        nas_volume_instance_no_list: Optional[List[str]] = None,
        region_no: Optional[str] = None,
        zone_no: Optional[str] = None,
    ) -> Dict:
        """Return Classic NAS volume instances without mutating resources."""

        params = {}
        if volume_allotment_protocol_type_code is not None:
            params["volumeAllotmentProtocolTypeCode"] = (
                volume_allotment_protocol_type_code
            )
        if is_event_configuration is not None:
            params["isEventConfiguration"] = is_event_configuration
        if is_snapshot_configuration is not None:
            params["isSnapshotConfiguration"] = is_snapshot_configuration
        if nas_volume_instance_no_list is not None:
            for index, instance_no in enumerate(
                nas_volume_instance_no_list,
                start=1,
            ):
                params[f"nasVolumeInstanceNoList.{index}"] = instance_no
        if region_no is not None:
            params["regionNo"] = region_no
        if zone_no is not None:
            params["zoneNo"] = zone_no

        return self.client.get("/getNasVolumeInstanceList", params=params)
