from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def update_yaml_values(
    config_dir: str | Path,
    file_name: str,
    updates: dict[str, Any],
) -> None:
    """更新 YAML 配置文件中的指定键，保留注释与格式。

    Args:
        config_dir: 配置目录路径
        file_name: 配置文件名（不含 .yml 后缀）
        updates: 嵌套键路径 → 值，键路径以点分隔（如 "p115.cookies"）

    Raises:
        FileNotFoundError: 配置文件不存在
    """
    config_path = Path(config_dir) / f"{file_name}.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    yaml = YAML()
    yaml.preserve_quotes = True

    with config_path.open(encoding="utf-8") as f:
        data = yaml.load(f) or {}

    for key_path, value in updates.items():
        keys = key_path.split(".")
        cursor = data
        for key in keys[:-1]:
            existing = cursor.get(key)
            if not isinstance(existing, dict):
                cursor[key] = {}
            cursor = cursor[key]
        cursor[keys[-1]] = value

    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
