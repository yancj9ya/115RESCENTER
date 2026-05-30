#!/usr/bin/env python
"""演示整理系统的完整流程"""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.organizing import MEDIA_KIND_MOVIE, MEDIA_KIND_SERIES, OrganizeMetadata, OrganizeRule
from src.organizing.repository import OrganizeRepository
from src.processors.organize_run import OrganizeRunService


class DemoStorage:
    """演示用的存储服务"""

    def __init__(self) -> None:
        self.staging_files = [
            {
                "id": 1001,
                "name": "Inception.2010.1080p.BluRay.mkv",
                "is_dir": False,
                "size": 2147483648,  # 2GB
            },
            {
                "id": 1002,
                "name": "Breaking.Bad.S01E01.1080p.mkv",
                "is_dir": False,
                "size": 1073741824,  # 1GB
            },
            {
                "id": 1003,
                "name": "Attack.on.Titan.S02E12.mkv",
                "is_dir": False,
                "size": 524288000,  # 500MB
            },
            {
                "id": 1004,
                "name": "Unknown.Movie.mkv",
                "is_dir": False,
                "size": 1048576000,  # 1000MB
            },
            {
                "id": 1005,
                "name": "Some.Folder",
                "is_dir": True,
                "size": 0,
            },
        ]
        self.operations = []
        self.created_folders = {}

    def list_folder(self, cid: int) -> list[dict]:
        """列出文件夹内容"""
        if cid == 9001:  # staging
            return self.staging_files
        # 目标目录返回空（无重复）
        return []

    def ensure_folder(self, parent_cid: int, name: str) -> dict:
        """确保文件夹存在"""
        key = (parent_cid, name)
        if key not in self.created_folders:
            folder_id = 2000 + len(self.created_folders)
            self.created_folders[key] = folder_id
            self.operations.append(f"创建文件夹: {name} (parent={parent_cid}, id={folder_id})")
        return {"id": self.created_folders[key], "name": name, "is_dir": True}

    def rename_file(self, file_id: int, new_name: str) -> dict:
        """重命名文件"""
        self.operations.append(f"重命名: file_id={file_id} -> {new_name}")
        return {"state": True}

    def move_file(self, file_id: int, target_cid: int) -> dict:
        """移动文件"""
        self.operations.append(f"移动: file_id={file_id} -> cid={target_cid}")
        return {"state": True}

    def delete_file(self, file_id: int) -> dict:
        """删除文件"""
        self.operations.append(f"删除: file_id={file_id}")
        return {"state": True}


def demo_metadata_resolver(item: dict) -> OrganizeMetadata | None:
    """演示用的元数据解析器"""
    file_id = item["id"]

    if file_id == 1001:  # Inception
        return OrganizeMetadata(
            title="Inception",
            year=2010,
            kind=MEDIA_KIND_MOVIE,
            tmdb_id=27205,
            region_category="欧美",
            genre_ids=(28, 878, 53),  # Action, Sci-Fi, Thriller
        )

    elif file_id == 1002:  # Breaking Bad
        return OrganizeMetadata(
            title="Breaking Bad",
            year=2008,
            kind=MEDIA_KIND_SERIES,
            season=1,
            episode=1,
            tmdb_id=1396,
            region_category="欧美",
            genre_ids=(18, 80),  # Drama, Crime
        )

    elif file_id == 1003:  # Attack on Titan
        return OrganizeMetadata(
            title="進撃の巨人",
            year=2013,
            kind=MEDIA_KIND_SERIES,
            season=2,
            episode=12,
            tmdb_id=1429,
            region_category="日韩",
            genre_ids=(16, 10759, 10765),  # Animation, Action, Sci-Fi
        )

    # file_id == 1004: Unknown.Movie.mkv - 返回 None（TMDB 解析失败）
    return None


def run_demo():
    """运行演示"""
    import sys
    import io

    # 设置 UTF-8 输出
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("115 资源中心 - 整理系统演示")
    print("=" * 80)
    print()

    # 创建临时数据库
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "demo.db"

        # 初始化
        print("[初始化] 初始化组件...")
        repository = OrganizeRepository(db_path)
        repository.init_schema()

        storage = DemoStorage()
        rule = OrganizeRule(media_library_root_cid=100)

        service = OrganizeRunService(
            repository=repository,
            storage=storage,
            rule=rule,
            metadata_resolver=demo_metadata_resolver,
        )

        print(f"  中转目录 CID: 9001")
        print(f"  媒体库根目录 CID: 100")
        print()

        # 显示待整理文件
        print("[文件列表] 中转目录文件:")
        print("-" * 80)
        for item in storage.staging_files:
            file_type = "[DIR]" if item["is_dir"] else "[FILE]"
            size_mb = item["size"] / (1024 * 1024)
            print(f"  {file_type} [{item['id']:4d}] {item['name']:<50} ({size_mb:.0f}MB)")
        print()

        # 执行整理
        print("[执行] 开始整理...")
        print("-" * 80)
        result = service.run_once(staging_cid=9001)
        print()

        # 显示结果统计
        print("[结果] 整理统计:")
        print("-" * 80)
        print(f"  状态: {result.status}")
        print(f"  扫描文件数: {result.scanned_count}")
        print(f"  计划整理: {result.planned_count}")
        print(f"  成功: {result.success_count}")
        print(f"  跳过: {result.skipped_count}")
        print(f"  失败: {result.failed_count}")
        if result.last_error:
            print(f"  最后错误: {result.last_error}")
        print()

        # 显示详细操作
        print("[操作] 执行的操作:")
        print("-" * 80)
        for i, op in enumerate(storage.operations, 1):
            print(f"  {i}. {op}")
        print()

        # 显示每个文件的处理结果
        print("[详情] 文件处理详情:")
        print("-" * 80)
        items = repository.list_run_items(result.run_id)
        for item in items:
            status_label = {
                "SUCCESS": "[OK]",
                "SKIPPED_DIR": "[SKIP-DIR]",
                "SKIPPED_UNMATCHED": "[SKIP-NOMETA]",
                "SKIPPED_DUPLICATE": "[SKIP-DUP]",
                "FAILED": "[FAIL]",
            }.get(item.status, "[?]")

            print(f"\n  {status_label} 文件 ID: {item.file_id}")
            print(f"     原始名称: {item.file_name}")

            if item.status == "SUCCESS":
                print(f"     新名称: {item.new_name}")
                print(f"     目标路径: {item.target_path}")
                print(f"     目标 CID: {item.target_cid}")
            elif item.status == "SKIPPED_DIR":
                print(f"     原因: {item.reason}")
            elif item.status == "SKIPPED_UNMATCHED":
                print(f"     原因: {item.reason}")
                print(f"     说明: 文件留在中转目录，等待手动处理")
            elif item.status == "FAILED":
                print(f"     错误: {item.error}")

            if item.metadata_json:
                print(f"     元数据: 已记录")

        print()
        print("=" * 80)
        print("演示完成！")
        print()
        print("[说明]")
        print("  - [OK] SUCCESS: 文件已成功整理并移动到媒体库")
        print("  - [SKIP-DIR] SKIPPED_DIR: 跳过目录")
        print("  - [SKIP-NOMETA] SKIPPED_UNMATCHED: TMDB 解析失败，留在中转目录")
        print("  - [SKIP-DUP] SKIPPED_DUPLICATE: 目标已存在更大文件，跳过")
        print("  - [FAIL] FAILED: 处理失败")
        print("=" * 80)


if __name__ == "__main__":
    run_demo()
