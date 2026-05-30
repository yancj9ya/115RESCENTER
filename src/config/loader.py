"""YAML 配置加载器

提供统一的配置加载接口，支持：
- 从 YAML 文件加载配置
- 配置验证和默认值
- 环境变量覆盖（可选）
- 配置合并
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    raise ImportError(
        "PyYAML is required for YAML configuration. "
        "Install it with: pip install pyyaml"
    )

_logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_dir: str | Path = "config") -> None:
        """初始化配置加载器

        Args:
            config_dir: 配置文件目录路径
        """
        self.config_dir = Path(config_dir)
        if not self.config_dir.exists():
            raise FileNotFoundError(f"配置目录不存在: {self.config_dir}")

    def load(self, config_name: str) -> dict[str, Any]:
        """加载指定的配置文件

        Args:
            config_name: 配置文件名（不含 .yml 后缀）

        Returns:
            配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML 解析错误
        """
        config_path = self.config_dir / f"{config_name}.yml"
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        return config

    def load_all(self) -> dict[str, Any]:
        """加载所有配置文件

        Returns:
            合并后的配置字典，键为配置文件名（不含后缀）
        """
        all_config = {}
        for config_file in self.config_dir.glob("*.yml"):
            config_name = config_file.stem
            try:
                all_config[config_name] = self.load(config_name)
            except Exception as e:
                _logger.warning("加载配置文件 %s 失败: %s", config_file, e)

        return all_config

    def get(self, config_name: str, key_path: str, default: Any = None) -> Any:
        """获取配置值（支持嵌套键）

        Args:
            config_name: 配置文件名
            key_path: 配置键路径，用点分隔，如 "p115.cookies"
            default: 默认值

        Returns:
            配置值，如果不存在则返回默认值

        Example:
            >>> loader = ConfigLoader()
            >>> cookies = loader.get("netdisk", "p115.cookies", "")
        """
        try:
            config = self.load(config_name)
            keys = key_path.split(".")
            value = config
            for key in keys:
                value = value[key]
            return value
        except (FileNotFoundError, KeyError, TypeError):
            return default

    def get_with_env_override(
        self,
        config_name: str,
        key_path: str,
        env_var: str,
        default: Any = None,
    ) -> Any:
        """获取配置值，支持环境变量覆盖

        Args:
            config_name: 配置文件名
            key_path: 配置键路径
            env_var: 环境变量名
            default: 默认值

        Returns:
            配置值，优先级：环境变量 > YAML 配置 > 默认值
        """
        # 优先使用环境变量
        env_value = os.getenv(env_var)
        if env_value is not None:
            return env_value

        # 其次使用 YAML 配置
        yaml_value = self.get(config_name, key_path)
        if yaml_value is not None:
            return yaml_value

        # 最后使用默认值
        return default


def create_default_config_loader() -> ConfigLoader:
    """创建默认的配置加载器

    Returns:
        ConfigLoader 实例

    Raises:
        FileNotFoundError: 配置目录不存在
    """
    # 尝试从项目根目录查找 config 目录
    current_dir = Path.cwd()
    config_dir = current_dir / "config"

    if not config_dir.exists():
        # 尝试从脚本所在目录的父目录查找
        script_dir = Path(__file__).parent.parent.parent
        config_dir = script_dir / "config"

    if not config_dir.exists():
        raise FileNotFoundError(
            f"找不到配置目录。请在以下位置之一创建 config 目录：\n"
            f"  - {current_dir / 'config'}\n"
            f"  - {script_dir / 'config'}"
        )

    return ConfigLoader(config_dir)


__all__ = [
    "ConfigLoader",
    "create_default_config_loader",
]
