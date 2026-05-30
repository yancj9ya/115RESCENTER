"""测试日志系统的脚本"""
import logging
import time

from src.logging_config import setup_logging

# 初始化日志系统
setup_logging()

logger = logging.getLogger(__name__)

def test_logging():
    """生成各种级别的测试日志"""

    logger.debug("这是一条 DEBUG 级别的日志 - 用于调试信息")
    time.sleep(0.5)

    logger.info("这是一条 INFO 级别的日志 - 正常信息")
    time.sleep(0.5)

    logger.warning("这是一条 WARNING 级别的日志 - 警告信息")
    time.sleep(0.5)

    logger.error("这是一条 ERROR 级别的日志 - 错误信息")
    time.sleep(0.5)

    # 模拟采集器日志
    logger.info("开始采集 Telegram 频道: @test_channel, 限制: 20 条消息")
    logger.info("解析到 5 条消息")
    logger.info("采集到分享链接: https://115.com/s/sw123456 (消息 12345)")
    logger.info("采集到分享链接: https://115.com/s/sw789012 (消息 12346)")
    logger.info("采集完成: @test_channel, 共采集到 2 个分享链接")

    time.sleep(0.5)

    # 模拟订阅匹配日志
    logger.info("匹配成功: 规则 '电影订阅' (ID: rule-001), 关键词: ['电影', '2024'], 链接: https://115.com/s/sw123456")

    time.sleep(0.5)

    # 模拟转存日志
    logger.info("开始转存分享: share_code=sw123456, target_cid=1234567890")
    logger.info("转存文件数量: 3, IDs: [111, 222, 333]")
    logger.info("转存成功: share_code=sw123456, 文件数: 3")

    time.sleep(0.5)

    # 模拟 TMDB 搜索日志
    logger.info("TMDB 电影搜索: query='流浪地球', year=2019")
    logger.info("TMDB 解析成功: '流浪地球' (2019), 地区: CN")

    logger.info("测试日志生成完成！")

if __name__ == "__main__":
    print("开始生成测试日志...")
    test_logging()
    print("测试日志已生成，请访问前端查看日志中心")
