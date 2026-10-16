# 合成表导出 (RecipeDumper) — 1.21.1 / NeoForge

为 [MC百科](https://www.mcmod.cn) 导出模组配方的工具。

原版 [RecipeDumper](https://www.mcmod.cn/class/4341.html) 由 **youyihj** 制作，只做到 1.20.6 就停更了。
这是用 **1.21.1 的配方 API 重写**的版本，**导出的 JSON 格式与原版保持一致**，这样百科那边不用改解析器。

---

## 用法

### 命令

在游戏里执行（单人游戏需要开启作弊）：

```
/dumprecipe <modid>
```

例如 `/dumprecipe armor_addon`。结果写到：

```
<游戏目录>/export/dump_recipes_<modid>.json
```

modid 有 Tab 补全。

### 无人值守

设环境变量后，服务端启动完成时会自动导出一次，方便脚本化 / CI：

```bash
RECIPEDUMPER_AUTO=armor_addon ./gradlew runServer
```

不设就什么都不发生。

---

## 导出格式

```json
{
  "recipes": [
    {
      "type": "crafting_shaped",
      "name": "armor_addon:iron_heavy_helmet",
      "input": {
        "1": { "item": "minecraft:iron_block", "count": 1 },
        "2": { "tag": "minecraft:wool", "count": 1 }
      },
      "output": {
        "1": { "item": "armor_addon:iron_heavy_helmet", "count": 1 }
      }
    }
  ],
  "error": []
}
```

`error` 里是导出失败的配方 id；单条失败不会中断整体。

### 槽位约定

| 配方类型 | `type` | 输入槽位 |
| --- | --- | --- |
| **有序合成** | `crafting_shaped` | 按 3×3 网格：左上角 1、右下角 9，即 `y * 3 + x + 1` |
| **无序合成** | `crafting_shapeless` | 从 1 顺次编号 |
| **锻造** | `minecraft:smithing_transform` | **基底 = 1、添加物 = 2、模板 = 3** |
| **烧炼** | `minecraft:smelting` 等 | 1，另带 `experience` / `cookTime` |
| **切石** | `minecraft:stonecutting` | 1 |

输出一律用槽位 1。

> **关于锻造的模板槽位**：1.16 的锻造只有基底和添加物，原版把基底放 1、添加物放 2。
> 1.21 多了模板，这里**沿用原版的 1/2 不动，把模板放到 3** —— 这样旧的解析器读 1/2 仍然正确。

> **关于 `type` 的命名空间**：有序 / 无序合成用原版写死的无命名空间名字
> （`crafting_shaped` / `crafting_shapeless`），其余用 `RecipeType` 的注册名（带命名空间）。
> 这个不一致是原版就有的，这里刻意不改，以免百科那边认不出来。

---

## 和原版的差异

| | 原版 (1.16~1.20.6) | 这里 (1.21.1) |
| --- | --- | --- |
| 导出框架 | 注解扫描 + 反射注册各类型的 dumper | 直接在代码里按类型分派 |
| 配方 API | `IRecipe` / `getRegistryName` / NBT | `Recipe` / `ResourceLocation` / 数据组件 |
| 锻造 | base=1、addition=2 | base=1、addition=2、**template=3** |
| 烧炼 | `getCookTime()` | `getCookingTime()` |
| 自动导出 | 无 | 支持 `RECIPEDUMPER_AUTO` 环境变量 |

**JSON 结构、槽位编号、`type` 命名都保持一致。**

### 关于 AccessTransformer

`SmithingTransformRecipe` 的 `template` / `base` / `addition` 三个字段是**包级私有**的，
跨包读不到，所以用了一个 AccessTransformer：

```
src/main/resources/META-INF/accesstransformer.cfg
```

ModDevGradle 用默认路径时不需要额外配置；`build.gradle` 里开了
`validateAccessTransformers = true`，写错目标会直接报错而不是静默失效。

---

## 构建

```bash
./gradlew build
```

产物在 `build/libs/RecipeDumper-<version>.jar`。

构建脚本沿用了 [armor-addon-neoforge](../armor-addon-neoforge) 的那套：
NeoForge 走 ForgeCDN 镜像、Mojang 资源走 BMCLAPI，适配国内网络。
注意 `mirror_port` 和那个工程错开（47822 vs 47821），避免同时运行时抢占端口。

---

## 验证

`tools/verify_dump.py` 做交叉验证：**从模组源码的配方文件推导期望值**，
和**游戏运行时导出的实际值**逐条对比（类型、槽位、输入、输出、数量）。

```bash
python tools/verify_dump.py run/export/dump_recipes_armor_addon.json
```

用它跑「盔甲附加」1.3.3 的 69 条配方，结果是 **69 条全部一致，0 不符 / 0 缺失 / 0 多余**。

---

## 许可

MIT。原版 RecipeDumper 的作者是 youyihj，本重写版沿用同一许可。
