from typing import Dict


SUPPORTED_REGIONS = {
    "gov": frozenset({"KR", "KRS"}),
    "public": frozenset({"KR", "SGN", "JPN"}),
}


BASE_ENDPOINTS: Dict[str, Dict[str, str]] = {
    "gov": {
        "ncloud": "https://ncloud.apigw.gov-ntruss.com",
        "certificatemanager": "https://certificatemanager.apigw.gov-ntruss.com",
        "cloudinsight": "https://cw.apigw.gov-ntruss.com",
        "cloudactivitytracer": "https://cloudactivitytracer.apigw.gov-ntruss.com",
        "securitymonitoring": "https://securitymonitoring.apigw.gov-ntruss.com",
        "cloudloganalytics": "https://cloudloganalytics.apigw.gov-ntruss.com",
        "subaccount": "https://subaccount.apigw.gov-ntruss.com",
        "resourcemanager": "https://resourcemanager.apigw.gov-ntruss.com",
        "webservicemonitor": "https://wms.apigw.gov-ntruss.com",
        "globaldns": "https://globaldns.apigw.gov-ntruss.com/dns/v1",
        "platform": "https://billingapi.apigw.gov-ntruss.com/billing/v1",
        
    },
    "public": {
        "ncloud": "https://ncloud.apigw.ntruss.com",
        "certificatemanager": "https://certificatemanager.apigw.ntruss.com",
        "cloudinsight": "https://cw.apigw.ntruss.com",
        "cloudactivitytracer": "https://cloudactivitytracer.apigw.ntruss.com",
        "securitymonitoring": "https://securitymonitoring.apigw.ntruss.com",
        "cloudloganalytics": "https://cloudloganalytics.apigw.ntruss.com",
        "subaccount": "https://subaccount.apigw.ntruss.com",
        "resourcemanager": "https://resourcemanager.apigw.ntruss.com",
        "webservicemonitor": "https://wms.apigw.ntruss.com",
        "globaldns": "https://globaldns.apigw.ntruss.com/dns/v1",
        "platform": "https://billingapi.apigw.ntruss.com/billing/v1",
        "organization": "https://organization.apigw.ntruss.com",
    },
}


def _validated_api_type_and_region(api_type: str, region: str) -> tuple[str, str]:
    if not isinstance(api_type, str) or not api_type.strip():
        raise ValueError("api_type은 비어 있지 않은 문자열이어야 합니다.")
    if not isinstance(region, str) or not region.strip():
        raise ValueError("region은 비어 있지 않은 문자열이어야 합니다.")

    normalized_api_type = api_type.strip().lower()
    normalized_region = region.strip().upper()

    if normalized_api_type not in BASE_ENDPOINTS:
        supported = ", ".join(sorted(BASE_ENDPOINTS))
        raise ValueError(
            f"지원하지 않는 api_type입니다: {api_type!r} (지원값: {supported})"
        )

    supported_regions = SUPPORTED_REGIONS[normalized_api_type]
    if normalized_region not in supported_regions:
        supported = ", ".join(sorted(supported_regions))
        raise ValueError(
            "지원하지 않는 region입니다: "
            f"{region!r} (api_type={normalized_api_type}, 지원값: {supported})"
        )

    return normalized_api_type, normalized_region


def get_kubernetes_endpoint(api_type: str, region: str) -> str:
    api_type, region = _validated_api_type_and_region(api_type, region)

    if api_type == "gov":
        if region == "KRS":
            return "https://nks.apigw.gov-ntruss.com/vnks/krs-v2"
        return "https://nks.apigw.gov-ntruss.com/vnks/v2"

    if region == "SGN":
        return "https://nks.apigw.ntruss.com/vnks/sgn-v2"

    if region == "JPN":
        return "https://nks.apigw.ntruss.com/vnks/jpn-v2"

    return "https://nks.apigw.ntruss.com/vnks/v2"


def build_api_endpoints(api_type: str, region: str) -> Dict[str, str]:
    api_type, region = _validated_api_type_and_region(api_type, region)

    base = BASE_ENDPOINTS[api_type]
    ncloud = base["ncloud"]

    return {
        "vserver": ncloud,
        "vpc": f"{ncloud}/vpc/v2",
        "loadbalancer": f"{ncloud}/vloadbalancer/v2",
        "vnas": f"{ncloud}/vnas/v2",
        "clouddb": ncloud,
        "certificatemanager": base["certificatemanager"],
        "cloudinsight": base["cloudinsight"],
        "cloudactivitytracer": base["cloudactivitytracer"],
        "securitymonitoring": base["securitymonitoring"],
        "cloudloganalytics": base["cloudloganalytics"],
        "subaccount": base["subaccount"],
        "resourcemanager": base["resourcemanager"],
        "webservicemonitor": base["webservicemonitor"],
        "globaldns": base["globaldns"],
        "platform": base["platform"],
        **({"organization": base["organization"]} if "organization" in base else {}),

        "kubernetes": get_kubernetes_endpoint(api_type, region),
    }
