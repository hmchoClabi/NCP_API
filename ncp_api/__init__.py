__all__ = [
    "SubAccountAPI",
    "VServerAPI",
    "PlatformAPI",
    "ContainerAPI",
    "KubernetesAPI",
    "VNasAPI",
    "NetworkAPI",
    "ResourceManagerAPI",
    "CloudLogAnalyticsAPI",
    "WebServiceMonitorAPI",
    "CloudInsightAPI",
    "CloudActivityTracerAPI",
    "CertificateMgrAPI"
]


def __getattr__(name):
    if name == "SubAccountAPI":
        from .subaccountAPI import SubAccountAPI
        return SubAccountAPI
    if name == "VServerAPI":
        from .vserverAPI import VServerAPI
        return VServerAPI
    if name == "PlatformAPI":
        from .platformAPI import PlatformAPI
        return PlatformAPI
    if name == "ContainerAPI":
        from .containerAPI import ContainerAPI
        return ContainerAPI
    if name == "KubernetesAPI":
        from .kubernetesAPI import KubernetesAPI
        return KubernetesAPI
    if name == "VNasAPI":
        from .vnasAPI import VNasAPI
        return VNasAPI
    if name == "NetworkAPI":
        from .networkAPI import NetworkAPI
        return NetworkAPI
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

    raise AttributeError(f"module 'ncp_api' has no attribute '{name}'")