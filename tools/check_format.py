#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查导出的 JSON 是否符合【原版 RecipeDumper】的格式约定。

原版是 1.16 的代码，MC百科那边的解析器是按它的输出写的。这里把原版源码里
体现出来的约定逐条抽出来，对导出结果做严格校验——只要全部通过，
就能确定这份 JSON 能被原版的解析器读下去。

原版的约定（来自 cn.mcmod.recipedumper 的源码）：

  顶层            { "recipes": [...], "error": [ "配方id", ... ] }
  每条配方        type / name / input / output 四个字段
  input           键是槽位号（字符串形式的整数），值 = ingredient JSON + count
  output          键是槽位号，值 = { "item": "ns:id", "count": N, "nbt"?: "..." }
  type            有序 = "crafting_shaped"、无序 = "crafting_shapeless"、
                  其余 = recipe.getType().toString()
  烧炼额外        experience / cookTime

用法：python tools/check_format.py <导出的json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 原版在 DUMPERS 里注册过的类型。
#
# 有序 / 无序是 dumper 里写死的；其余走 recipe.getType().toString()。
# 而 RecipeType 的 toString() 返回的是【注册时传的短名】——
#   public class RecipeType<T> implements IRecipeType<T> {
#       private final String toString;
#       public RecipeType(String name) { this.toString = name; }
#       public String toString() { return this.toString; }
#   }
# 所以锻造是 "smithing" 而不是 "minecraft:smithing_transform"。
# 带命名空间的写法也一并认下，免得别的整合环境里冒出全名被误报。
KNOWN_TYPES = {
    "crafting_shaped", "crafting_shapeless",
    "smithing", "smelting", "blasting", "smoking", "campfire_cooking", "stonecutting",
    "minecraft:smithing", "minecraft:smithing_transform",
    "minecraft:smelting", "minecraft:blasting", "minecraft:smoking",
    "minecraft:campfire_cooking", "minecraft:stonecutting",
}

# 有序 / 无序这两个是原版写死的，必须精确命中
STRICT_TYPES = {"crafting_shaped", "crafting_shapeless"}

REQUIRED_RECIPE_KEYS = {"type", "name", "input", "output"}
OPTIONAL_RECIPE_KEYS = {"experience", "cookTime"}

# ingredient 可能的写法（原版用 Ingredient#serialize，1.21 用 Ingredient.CODEC）
INGREDIENT_KEYS = {"item", "tag", "items", "ingredient", "type"}

OUTPUT_KEYS = {"item", "count", "nbt", "components"}


def is_slot_key(key: str) -> bool:
    return key.isdigit() and int(key) >= 1


def check(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []

    # ---- 顶层 ----
    if set(data.keys()) != {"recipes", "error"}:
        errors.append(f"顶层键应为 recipes + error，实际 {sorted(data.keys())}")
    if not isinstance(data.get("recipes"), list):
        errors.append("recipes 不是数组")
    if not isinstance(data.get("error"), list):
        errors.append("error 不是数组")

    recipes = data.get("recipes", [])
    print(f"  文件: {path.name}")
    print(f"  配方数: {len(recipes)}    error 条目: {len(data.get('error', []))}")
    print()

    type_counter: dict[str, int] = {}

    for i, r in enumerate(recipes):
        tag = r.get("name", f"#{i}")

        # ---- 字段集 ----
        keys = set(r.keys())
        missing = REQUIRED_RECIPE_KEYS - keys
        extra = keys - REQUIRED_RECIPE_KEYS - OPTIONAL_RECIPE_KEYS
        if missing:
            errors.append(f"{tag}: 缺字段 {sorted(missing)}")
        if extra:
            errors.append(f"{tag}: 多了原版没有的字段 {sorted(extra)}")

        # ---- type ----
        rtype = r.get("type", "")
        type_counter[rtype] = type_counter.get(rtype, 0) + 1
        if rtype not in KNOWN_TYPES:
            warnings.append(f"{tag}: type={rtype!r} 不在原版已知集合里")

        # ---- name ----
        name = r.get("name", "")
        if ":" not in name:
            errors.append(f"{tag}: name 不是完整的命名空间 id（原版用 recipe.getId().toString()）")

        # ---- input ----
        inp = r.get("input")
        if not isinstance(inp, dict):
            errors.append(f"{tag}: input 不是对象")
        else:
            for slot, ing in inp.items():
                if not is_slot_key(slot):
                    errors.append(f"{tag}: input 的键 {slot!r} 不是从 1 开始的槽位号")
                if not isinstance(ing, dict):
                    if isinstance(ing, list):
                        warnings.append(f"{tag}: 槽位 {slot} 的 ingredient 是数组（多选一），原版会当对象处理")
                    else:
                        errors.append(f"{tag}: 槽位 {slot} 的 ingredient 不是对象")
                    continue
                if not (set(ing.keys()) & INGREDIENT_KEYS):
                    errors.append(f"{tag}: 槽位 {slot} 的 ingredient 里没有 item/tag 之类的键：{sorted(ing.keys())}")
                if "count" not in ing:
                    errors.append(f"{tag}: 槽位 {slot} 的 ingredient 缺 count（原版会补上）")

        # ---- output ----
        out = r.get("output")
        if not isinstance(out, dict):
            errors.append(f"{tag}: output 不是对象")
        else:
            if "1" not in out:
                errors.append(f"{tag}: output 里没有槽位 1（原版默认写槽位 1）")
            for slot, stack in out.items():
                if not is_slot_key(slot):
                    errors.append(f"{tag}: output 的键 {slot!r} 不是从 1 开始的槽位号")
                if not isinstance(stack, dict):
                    errors.append(f"{tag}: output 槽位 {slot} 不是对象")
                    continue
                unknown = set(stack.keys()) - OUTPUT_KEYS
                if unknown:
                    errors.append(f"{tag}: output 槽位 {slot} 多了字段 {sorted(unknown)}")
                if "item" not in stack:
                    errors.append(f"{tag}: output 槽位 {slot} 缺 item")
                elif ":" not in str(stack["item"]):
                    errors.append(f"{tag}: output 槽位 {slot} 的 item 不是完整 id")
                if "count" not in stack:
                    errors.append(f"{tag}: output 槽位 {slot} 缺 count")
                elif not isinstance(stack["count"], int) or stack["count"] < 1:
                    errors.append(f"{tag}: output 槽位 {slot} 的 count 非法：{stack['count']!r}")

        # ---- 烧炼的额外字段 ----
        if "smelting" in rtype or "blasting" in rtype or "smoking" in rtype or "campfire" in rtype:
            for k in ("experience", "cookTime"):
                if k not in r:
                    warnings.append(f"{tag}: 是 {rtype} 但缺 {k}")

    # ---- 汇总 ----
    print("  类型分布:")
    for t, n in sorted(type_counter.items()):
        mark = "✓" if t in KNOWN_TYPES else "?"
        print(f"    {mark} {t:<36} {n}")
    print()

    if errors:
        print(f"  ❌ 错误 {len(errors)} 条:")
        for e in errors[:30]:
            print(f"      {e}")
        if len(errors) > 30:
            print(f"      ...还有 {len(errors)-30} 条")
    else:
        print("  ✅ 结构校验全部通过 —— 原版形式的解析器可以直接读这份文件")

    if warnings:
        print()
        print(f"  ⚠️  提示 {len(warnings)} 条:")
        for w in warnings[:15]:
            print(f"      {w}")
        if len(warnings) > 15:
            print(f"      ...还有 {len(warnings)-15} 条")

    return 1 if errors else 0


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("用法: python tools/check_format.py <导出的json>")

    sys.exit(check(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
