#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交叉验证：把 RecipeDumper 导出的 JSON 和源配方文件逐条对比。

两边的来源完全独立：
  期望值 —— 直接读模组源码里的 recipe/*.json
  实际值 —— 由游戏运行时导出

所以能真正验出「导出的东西对不对」，而不是自己跟自己对。

只比对逻辑等价性：把每个 ingredient 归一化成可比较的字符串，
再比较哪个槽位放了什么、输出是什么、数量多少。

用法：
    python tools/verify_dump.py <导出的json> [<recipe目录或模组源码目录>]

第二个参数省略时，会在本工程及其同级目录里找唯一一个含
data/<modid>/recipe 的模组源码目录。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
RECIPE_DIR = PROJ / "src/main/resources/data/armor_addon/recipe"


def auto_find_recipe_dir() -> Path | None:
    """在同级目录里找一个含 data/<modid>/recipe 的模组源码目录。"""
    candidates: list[Path] = []
    base = PROJ.parent
    for sibling in sorted(base.iterdir()):
        data = sibling / "src/main/resources/data"
        if not data.is_dir():
            continue
        for mod in sorted(data.iterdir()):
            recipe = mod / "recipe"
            if recipe.is_dir() and any(recipe.glob("*.json")):
                candidates.append(recipe)

    # 正好一个才敢自动用，多个就得让调用者明确指定
    return candidates[0] if len(candidates) == 1 else None


def normalize_ingredient(obj) -> str:
    """把一个 ingredient 归一化成可比较的字符串。

    支持源配方里可能出现的几种写法，以及导出侧由 Ingredient.CODEC 产生的写法：
        {"item": "ns:id"}
        {"tag": "ns:tag"}
        {"items": ["a", "b"]}
        [ {...}, {...} ]          多选一
    """
    if obj is None:
        return "EMPTY"

    if isinstance(obj, list):
        return "ANY(" + "|".join(sorted(normalize_ingredient(x) for x in obj)) + ")"

    if isinstance(obj, str):
        return obj

    if isinstance(obj, dict):
        if "item" in obj:
            return obj["item"]
        if "tag" in obj:
            return "#" + obj["tag"]
        if "items" in obj:
            return "ANY(" + "|".join(sorted(obj["items"])) + ")"
        if "ingredient" in obj:
            return normalize_ingredient(obj["ingredient"])
        # 其他形式（自定义 ingredient）就原样序列化，至少能比出差异
        return json.dumps(obj, sort_keys=True, ensure_ascii=False)

    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def normalize_result(obj) -> tuple[str, int]:
    """配方结果 → (物品 id, 数量)。1.21 用 "id"，旧版用 "item"。"""
    if obj is None:
        return ("EMPTY", 0)
    item = obj.get("id") or obj.get("item") or ""
    return (item, int(obj.get("count", 1)))


def expected_from_source(path: Path) -> dict:
    """从源配方文件算出期望的 type / input / output。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    rtype = data["type"].split(":")[-1]
    inputs: dict[str, str] = {}

    if rtype == "crafting_shaped":
        pattern = data["pattern"]
        key = data["key"]
        for y, row in enumerate(pattern):
            for x, ch in enumerate(row):
                if ch == " ":
                    continue
                inputs[str(y * 3 + x + 1)] = normalize_ingredient(key[ch])
        out_type = "crafting_shaped"
    elif rtype == "crafting_shapeless":
        for i, ing in enumerate(data["ingredients"]):
            inputs[str(i + 1)] = normalize_ingredient(ing)
        out_type = "crafting_shapeless"
    elif rtype == "smithing_transform":
        # 导出侧：base=1、addition=2、template=3
        if "base" in data:
            inputs["1"] = normalize_ingredient(data["base"])
        if "addition" in data:
            inputs["2"] = normalize_ingredient(data["addition"])
        if "template" in data:
            inputs["3"] = normalize_ingredient(data["template"])
        out_type = "smithing"  # 游戏里 RecipeType.SMITHING 就叫这个
    elif rtype == "smithing":
        # 1.20 之前的旧式锻造（没有模板）
        if "base" in data:
            inputs["1"] = normalize_ingredient(data["base"])
        if "addition" in data:
            inputs["2"] = normalize_ingredient(data["addition"])
        out_type = "smithing"
    else:
        out_type = rtype

    item, count = normalize_result(data.get("result"))
    return {"type": out_type, "input": inputs, "output": {"1": (item, count)}}


def actual_from_dump(entry: dict) -> dict:
    """把导出的一条记录归一化成同样的形状。"""
    inputs = {}
    for slot, ing in entry.get("input", {}).items():
        # 导出侧把 count 塞进了 ingredient 对象，归一化时忽略它
        ing = {k: v for k, v in ing.items() if k != "count"} if isinstance(ing, dict) else ing
        inputs[str(slot)] = normalize_ingredient(ing)

    outputs = {}
    for slot, stack in entry.get("output", {}).items():
        outputs[str(slot)] = (stack.get("item", ""), int(stack.get("count", 1)))

    return {"type": entry.get("type"), "input": inputs, "output": outputs}


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("用法: python tools/verify_dump.py <导出的json> [<recipe目录>]")

    global RECIPE_DIR
    if len(sys.argv) >= 3:
        given = Path(sys.argv[2])
        # 允许直接给模组源码根目录
        if (given / "src/main/resources/data").is_dir():
            found = list(given.glob("src/main/resources/data/*/recipe"))
            if not found:
                raise SystemExit(f"{given} 里找不到 data/<modid>/recipe")
            RECIPE_DIR = found[0]
        else:
            RECIPE_DIR = given
    elif not RECIPE_DIR.is_dir():
        auto = auto_find_recipe_dir()
        if auto is None:
            raise SystemExit("猜不出 recipe 目录，请作为第二个参数传入")
        RECIPE_DIR = auto

    dump_path = Path(sys.argv[1])
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    sources = {p.stem: p for p in RECIPE_DIR.glob("*.json")}

    print(f"  源配方目录: {RECIPE_DIR}")
    print(f"  源配方文件: {len(sources)} 个")
    print(f"  导出记录:   {len(dump['recipes'])} 条")
    print()

    by_name = {r["name"]: r for r in dump["recipes"]}
    ok = mismatch = missing = 0
    problems: list[str] = []

    for name, path in sorted(sources.items()):
        full = f"armor_addon:{name}"
        if full not in by_name:
            missing += 1
            problems.append(f"[缺失] {name} 没出现在导出里")
            continue

        want = expected_from_source(path)
        got = actual_from_dump(by_name[full])

        diffs = []
        if want["type"] != got["type"]:
            diffs.append(f"type  期望 {want['type']!r} 实际 {got['type']!r}")
        if want["input"] != got["input"]:
            all_slots = sorted(set(want["input"]) | set(got["input"]), key=lambda s: int(s))
            for s in all_slots:
                a, b = want["input"].get(s), got["input"].get(s)
                if a != b:
                    diffs.append(f"槽位 {s}  期望 {a!r} 实际 {b!r}")
        if want["output"] != got["output"]:
            diffs.append(f"输出  期望 {want['output']} 实际 {got['output']}")

        if diffs:
            mismatch += 1
            problems.append(f"[不符] {name}\n        " + "\n        ".join(diffs))
        else:
            ok += 1

    # 导出里有、源文件里没有的
    extra = [n for n in by_name if n.split(":")[-1] not in sources]

    print(f"  一致: {ok}    不符: {mismatch}    缺失: {missing}    多余: {len(extra)}")
    print()

    if problems:
        print("  问题明细:")
        for p in problems[:40]:
            print(f"    {p}")
        if len(problems) > 40:
            print(f"    ...还有 {len(problems)-40} 条")
    else:
        print("  ✅ 全部一致")

    if extra:
        print()
        print("  导出中存在但源目录没有的:")
        for n in extra[:10]:
            print(f"    {n}")


if __name__ == "__main__":
    main()
