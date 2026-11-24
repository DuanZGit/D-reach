#!/usr/bin/env python3
"""Canonical D-Reach default-route config parser for fanout, plugin, and gateway."""

import argparse
import json
import re
import sys
from pathlib import Path


def parse_routes(script_path: Path, base_arg: str, deep_arg: str):
    source = script_path.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^SECTIONS = \[\n(.*?)^\]", source)
    if not match:
        raise ValueError("Could not parse SECTIONS route registry")

    entries = []
    for entry in re.split(r"\n(?=    \()", match.group(1)):
        label = re.match(r'\s*\("([a-z]+)",\s*"([^"]+)"', entry)
        if not label:
            continue
        deep = re.search(r",\s*(True|False)\s*\)", entry)
        entries.append(
            {
                "key": label.group(1),
                "name": label.group(2),
                "tier": "deep" if deep and deep.group(1) == "True" else "base",
            }
        )

    base_keys = base_arg.split()
    deep_keys = deep_arg.split()
    if not entries:
        raise ValueError("No route entries found in SECTIONS")
    if len(set(base_keys)) != len(base_keys) or len(set(deep_keys)) != len(deep_keys):
        raise ValueError("Duplicate route key in BASE_CHANNELS or DEEP_CHANNELS")
    if set(base_keys) & set(deep_keys):
        raise ValueError("Route key appears in both BASE_CHANNELS and DEEP_CHANNELS")
    route_keys = {entry["key"] for entry in entries}
    if route_keys != set(base_keys) | set(deep_keys):
        raise ValueError("SECTIONS does not match BASE_CHANNELS and DEEP_CHANNELS")
    for entry in entries:
        expected_tier = "deep" if entry["key"] in set(deep_keys) else "base"
        if entry["tier"] != expected_tier:
            raise ValueError(f"Route tier mismatch for {entry['key']}")
    return entries, base_keys, deep_keys


def read_list(config, name, allowed):
    values = config.get(name)
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{name} 必须是字符串数组")

    result = []
    allowed_set = set(allowed)
    for raw in values:
        value = raw.strip()
        if not value or "," in value:
            raise ValueError(f"{name} 每项必须是一个通道名")
        if value not in allowed_set:
            raise ValueError(f"{name} 含不适用的通道：{value}")
        if value not in result:
            result.append(value)
    return result


def load_data(script_path: Path, defaults_path: Path, base_arg: str, deep_arg: str):
    entries, base_keys, deep_keys = parse_routes(script_path, base_arg, deep_arg)
    try:
        try:
            raw_config = defaults_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            enabled_base, enabled_deep = base_keys, deep_keys
        else:
            config = json.loads(raw_config)
            if not isinstance(config, dict):
                raise ValueError("配置顶层必须是对象")
            enabled_base = read_list(config, "enabledByDefault", base_keys)
            enabled_deep = read_list(config, "enabledForDeep", deep_keys)
        error = ""
    except Exception as exc:
        enabled_base, enabled_deep = [], []
        error = str(exc)

    base_set, deep_set = set(enabled_base), set(enabled_deep)
    channels = []
    for entry in entries:
        is_deep = entry["tier"] == "deep"
        channels.append(
            {
                **entry,
                "default_on": not is_deep and entry["key"] in base_set,
                "deep_on": is_deep and entry["key"] in deep_set,
            }
        )
    return {
        "enabledByDefault": enabled_base,
        "enabledForDeep": enabled_deep,
        "defaults_error": error,
        "channels": channels,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True, type=Path)
    parser.add_argument("--defaults", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--deep", required=True)
    parser.add_argument("--format", choices=("json", "table", "lists"), required=True)
    args = parser.parse_args()

    try:
        data = load_data(args.script, args.defaults, args.base, args.deep)
    except Exception as exc:
        data = {
            "enabledByDefault": [],
            "enabledForDeep": [],
            "defaults_error": str(exc),
            "channels": [],
        }

    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.format == "lists":
        if data["defaults_error"]:
            print(data["defaults_error"], file=sys.stderr)
            return 2
        print(",".join(data["enabledByDefault"]) + "|" + ",".join(data["enabledForDeep"]))
        return 0

    for channel in data["channels"]:
        if channel["tier"] == "deep":
            state = " [deep-on]" if channel["deep_on"] else " [not-deep]"
        else:
            state = " [default-on]" if channel["default_on"] else " [not-default]"
        print(f"  {channel['key']:10s} {channel['tier']:4s}  {channel['name']}{state}")
    if data["defaults_error"]:
        print(f"\n  默认启用配置有误：{data['defaults_error']}")
    print('\n  用法: fanout.sh "<query>" [--deep] [--n N] [--on key1,key2] [--en "<english>"]')
    return 2 if data["defaults_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
