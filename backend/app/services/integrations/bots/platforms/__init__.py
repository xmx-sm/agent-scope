"""机器人平台适配器。"""

from app.services.integrations.bots.platforms.webhook import WebhookAdapter

_ADAPTERS = {"webhook": WebhookAdapter}


def _get_adapter(platform: str):
    """返回指定平台的适配器。"""
    adapter = _ADAPTERS.get(platform)
    if adapter is None:
        raise ValueError(f"暂不支持平台 {platform}")
    return adapter()
