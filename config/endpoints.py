from typing import Dict


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
    },
}


def get_containerregistry_endpoint(api_type: str, region: str) -> str:
    if api_type == "gov":
        if region == "KRS":
            return "https://gov-ncr.apigw.gov-ntruss.com/ncr/krs"
        return "https://gov-ncr.apigw.gov-ntruss.com/ncr/kr"

    if region == "SGN":
        return "https://ncr.apigw.ntruss.com/ncr/sgn-api/v2"

    if region == "JPN":
        return "https://ncr.apigw.ntruss.com/ncr/jpn-api/v2"

    return "https://ncr.apigw.ntruss.com/ncr/api/v2"


def get_kubernetes_endpoint(api_type: str, region: str) -> str:
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
    if api_type not in BASE_ENDPOINTS:
        raise ValueError(f"지원하지 않는 api_type입니다: {api_type}")

    base = BASE_ENDPOINTS[api_type]
    ncloud = base["ncloud"]

    return {
        "vserver": ncloud,
        "vpc": f"{ncloud}/vpc/v2",
        "loadbalancer": f"{ncloud}/vloadbalancer/v2",
        "vnas": f"{ncloud}/vnas/v2",
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

        "containerregistry": get_containerregistry_endpoint(api_type, region),
        "kubernetes": get_kubernetes_endpoint(api_type, region),
    }