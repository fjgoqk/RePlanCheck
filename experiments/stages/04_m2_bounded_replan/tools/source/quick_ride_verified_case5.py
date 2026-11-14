def main(start_point: str, end_point: str) -> float:
    """Pre-approved QuickRide pricing mirror — 边界案例（case 5）专用中毒版。

    模拟「替代工具亦失效」：返回格式错误的字符串，无法通过输出模式验证。
    预期：M2 的修复尝试失败 → 显式降级（partial_success），完整完成 0/30。
    """
    return {"result": "FARE_SERVICE_UNAVAILABLE"}
