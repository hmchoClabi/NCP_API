from typing import Any

from ncp_api import (
    SubAccountAPI,
    VserverAPI,
    PlatformAPI,
    ContainerAPI,
    KubernetesAPI,
    VnasAPI,
    GlobaldnsAPI,
    ResourceManagerAPI,
    CloudLogAnalyticsAPI,
    WebServiceMonitorAPI,
    CloudInsightAPI,
    CloudActivityTracerAPI,
    CertificateMgrAPI,
    VpcAPI,
    LoadbalancerAPI,
)


class APIFactory:
    """
    NCP API 객체를 필요한 시점에만 생성하고 재사용하는 Factory
    """

    def __init__(self):
        self._cache: dict[str, Any] = {}

        self._registry = {
            "sub_account": SubAccountAPI,
            "vserver": VserverAPI,
            "platform": PlatformAPI,
            "container": ContainerAPI,
            "kubernetes": KubernetesAPI,
            "vnas": VnasAPI,
            "global_dns": GlobaldnsAPI,
            "resource_manager": ResourceManagerAPI,
            "cloud_log_analytics": CloudLogAnalyticsAPI,
            "web_service_monitor": WebServiceMonitorAPI,
            "cloud_insight": CloudInsightAPI,
            "cloud_activity_tracer": CloudActivityTracerAPI,
            "certificate_manager": CertificateMgrAPI,
            "vpc": VpcAPI,
            "loadbalancer": LoadbalancerAPI,
        }

    def get(self, name: str):
        """
        API 객체를 반환합니다.
        최초 호출 시 생성하고, 이후에는 캐시된 객체를 반환합니다.
        """

        if name not in self._registry:
            available = ", ".join(sorted(self._registry.keys()))
            raise KeyError(
                f"지원하지 않는 API입니다: {name}. "
                f"사용 가능 API: {available}"
            )

        if name not in self._cache:
            api_class = self._registry[name]
            self._cache[name] = api_class()

        return self._cache[name]

    def clear_cache(self) -> None:
        """
        생성된 API 객체 캐시를 초기화합니다.
        """

        self._cache.clear()

    def available_apis(self) -> list[str]:
        """
        등록된 API 이름 목록을 반환합니다.
        """

        return sorted(self._registry.keys())