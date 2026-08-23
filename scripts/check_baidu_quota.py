#!/usr/bin/env python3
"""Check Baidu AI Search quota status for agent-reach routing.

v2.0: 升级到 quota_manager.py，覆盖全部 27 个工具（不仅搜索）
"""
import sys
import os
from pathlib import Path

# Add the skill's scripts directory to path
# agent-reach 和 baiduaisearchwithquota 是同级目录
skill_scripts = Path("/var/minis/skills/baiduaisearchwithquota/scripts")
sys.path.insert(0, str(skill_scripts))

try:
    # 用 quota_manager 替代旧 smart_search（覆盖全部 27 个工具）
    from quota_manager import QUOTA, CATEGORIES

    print("QUOTA_STATUS (27 tools, 7 categories):")
    warnings = []
    depleted_count = 0
    total_count = 0

    # 按分类输出
    for cat_key, cat_name in CATEGORIES.items():
        print(f"\n【{cat_name}】")
        for key, data in QUOTA.items():
            if data['category'] != cat_key:
                continue
            used = data['used']
            limit = data['limit']
            unit = data.get('unit', '次')
            total_count += 1

            if limit == 0:
                print(f"  {data['name']}: ❌ 未开通")
                continue

            remaining = limit - used
            pct = (used / limit * 100) if limit > 0 else 0
            warn = ""
            if remaining == 0:
                warn = " [DEPLETED]"
                depleted_count += 1
                warnings.append(f"[DEPLETED] {data['name']} 0/{limit}")
            elif remaining <= limit * 0.2:
                warn = " [WARNING]"
                warnings.append(f"[WARNING] {data['name']} 仅剩 {remaining}/{limit} ({pct:.0f}%)")
            print(f"  {data['name']}: {remaining}/{limit} {unit}{warn}")

    # 告警汇总
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  {w}")

    print(f"\nSUMMARY: {total_count - depleted_count}/{total_count} available, "
          f"{depleted_count} depleted")

    # 退出码：0 = 全部可用，1 = 部分用完，2 = 全部用完
    if depleted_count == 0:
        sys.exit(0)
    elif depleted_count >= total_count:
        sys.exit(2)
    else:
        sys.exit(1)

except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
