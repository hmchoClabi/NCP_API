__all__ = [
    "SubAccountAPI",
    "VserverAPI",
    "PlatformAPI",
    "ContainerAPI",
    "KubernetesAPI",
    "VnasAPI",
    "GlobaldnsAPI",
    "ResourceManagerAPI",
    "CloudLogAnalyticsAPI",
    "WebServiceMonitorAPI",
    "CloudInsightAPI",
    "CloudActivityTracerAPI",
    "CertificateMgrAPI",
    "VpcAPI",
    "LoadbalancerAPI"
]


def __getattr__(name):
    if name == "SubAccountAPI":
        from .subaccountAPI import SubAccountAPI
        return SubAccountAPI
    if name == "VserverAPI":
        from .vserverAPI import VserverAPI
        return VserverAPI
    if name == "PlatformAPI":
        from .platformAPI import PlatformAPI
        return PlatformAPI
    if name == "ContainerAPI":
        from .containerAPI import ContainerAPI
        return ContainerAPI
    if name == "KubernetesAPI":
        from .kubernetesAPI import KubernetesAPI
        return KubernetesAPI
    if name == "VnasAPI":
        from .vnasAPI import VnasAPI
        return VnasAPI
    if name == "GlobaldnsAPI":
        from .globaldnsAPI import GlobaldnsAPI
        return GlobaldnsAPI
    if name == "ResourceManagerAPI":
        from .resourcemgrAPI import ResourceManagerAPI
        return ResourceManagerAPI
    if name == "CloudLogAnalyticsAPI":
        from .claAPI import CloudLogAnalyticsAPI
        return CloudLogAnalyticsAPI
    if name == "WebServiceMonitorAPI":
        from .webservicemonitorAPI import WebServiceMonitorAPI
        return WebServiceMonitorAPI
    if name == "CloudInsightAPI":
        from .cloudinsightAPI import CloudInsightAPI
        return CloudInsightAPI
    if name == "CloudActivityTracerAPI":
        from .cloudactivitytracerAPI import CloudActivityTracerAPI
        return CloudActivityTracerAPI
    if name == "SecurityMonitoringAPI":
        from .securityAPI import SecurityMonitoringAPI
        return SecurityMonitoringAPI
    if name == "CertificateMgrAPI":
        from .certificateMgrAPI import CertificateMgrAPI
        return CertificateMgrAPI
    if name == "VpcAPI":
        from .vpcAPI import VpcAPI
        return VpcAPI
    if name == "LoadbalancerAPI":
        from .loadbalancerAPI import LoadbalancerAPI
        return LoadbalancerAPI

    raise AttributeError(f"module 'ncp_api' has no attribute '{name}'")