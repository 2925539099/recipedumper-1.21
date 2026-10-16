package cn.mcmod.recipedumper;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.serialization.JsonOps;

import net.minecraft.core.HolderLookup;
import net.minecraft.core.NonNullList;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.AbstractCookingRecipe;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.item.crafting.ShapedRecipe;
import net.minecraft.world.item.crafting.ShapelessRecipe;
import net.minecraft.world.item.crafting.SmithingTransformRecipe;

/**
 * 把一条配方转成 MC百科认识的 JSON。
 *
 * <p>格式完全照搬原版 RecipeDumper（1.16 版），这样百科那边的解析器不用改：</p>
 *
 * <pre>
 * {
 *   "type":   "crafting_shaped",
 *   "name":   "armor_addon:iron_heavy_helmet",
 *   "input":  { "1": { "item": "minecraft:iron_block" }, "2": { "tag": "minecraft:wool" } },
 *   "output": { "1": { "item": "armor_addon:iron_heavy_helmet", "count": 1 } }
 * }
 * </pre>
 *
 * <h2>槽位编号</h2>
 * <ul>
 *   <li><strong>有序合成</strong>：按 3×3 网格铺开，左上角是 1、右下角是 9，
 *       即 {@code y * 3 + x + 1}。这一步和原版一致，百科那边靠它还原摆放形状。</li>
 *   <li><strong>无序合成</strong>：从 1 开始顺次编号。</li>
 *   <li><strong>锻造</strong>：基底 = 1、添加物 = 2，与原版相同；
 *       1.21 新增的模板放在 <strong>3</strong>，这样旧解析器读 1/2 仍然正确。</li>
 *   <li><strong>烧炼 / 切石</strong>：输入 1、输出 1。</li>
 * </ul>
 *
 * <p>输出统一用槽位 1。</p>
 */
public final class RecipeJson {
	private RecipeJson() {
	}

	public static JsonObject toJson(RecipeHolder<?> holder, HolderLookup.Provider registries) {
		Recipe<?> recipe = holder.value();

		JsonObject json = new JsonObject();
		json.addProperty("type", typeName(recipe));
		json.addProperty("name", holder.id().toString());
		json.add("input", inputs(recipe));
		json.add("output", outputs(recipe, registries));

		// 烧炼类额外带经验与耗时，和原版一样
		if (recipe instanceof AbstractCookingRecipe cooking) {
			json.addProperty("experience", cooking.getExperience());
			json.addProperty("cookTime", cooking.getCookingTime());
		}

		return json;
	}

	/**
	 * 配方类型名。
	 *
	 * <p>有序 / 无序合成用原版写死的无命名空间名字；其余用 {@code RecipeType} 的注册名
	 * （1.21 的 {@code RecipeType#toString} 就返回注册名，如 {@code minecraft:smithing_transform}）。
	 * 这个"有的带命名空间、有的不带"的不一致是原版就有的，这里刻意不改，以免百科那边认不出来。</p>
	 */
	private static String typeName(Recipe<?> recipe) {
		if (recipe instanceof ShapedRecipe) {
			return "crafting_shaped";
		}
		if (recipe instanceof ShapelessRecipe) {
			return "crafting_shapeless";
		}
		return recipe.getType().toString();
	}

	private static JsonObject inputs(Recipe<?> recipe) {
		JsonObject json = new JsonObject();

		if (recipe instanceof ShapedRecipe shaped) {
			int width = shaped.getWidth();
			NonNullList<Ingredient> ingredients = shaped.getIngredients();

			for (int i = 0; i < ingredients.size(); i++) {
				// 配方里的 ingredients 是一维的（按行铺开），换算成 3×3 网格的槽位
				addIngredient(json, i / width * 3 + i % width + 1, ingredients.get(i));
			}
		} else if (recipe instanceof ShapelessRecipe shapeless) {
			NonNullList<Ingredient> ingredients = shapeless.getIngredients();

			for (int i = 0; i < ingredients.size(); i++) {
				addIngredient(json, i + 1, ingredients.get(i));
			}
		} else if (recipe instanceof SmithingTransformRecipe smithing) {
			// 这三个字段是包级私有，靠 accesstransformer.cfg 打开
			addIngredient(json, 1, smithing.base);
			addIngredient(json, 2, smithing.addition);
			addIngredient(json, 3, smithing.template);
		} else {
			// 烧炼、切石，以及以后可能加的其他单输入配方
			NonNullList<Ingredient> ingredients = recipe.getIngredients();

			for (int i = 0; i < ingredients.size(); i++) {
				addIngredient(json, i + 1, ingredients.get(i));
			}
		}

		return json;
	}

	/** 把一个 Ingredient 写进指定槽位。空白槽位直接跳过。 */
	private static void addIngredient(JsonObject json, int slot, Ingredient ingredient) {
		if (ingredient == null || ingredient.hasNoItems()) {
			return;
		}

		JsonElement element = Ingredient.CODEC
				.encodeStart(JsonOps.INSTANCE, ingredient)
				.result()
				.orElse(null);

		if (element == null) {
			return;
		}

		// 原版把数量塞进 ingredient 对象里；如果编码结果是个数组（多选一）就原样放着
		if (element.isJsonObject()) {
			element.getAsJsonObject().addProperty("count", 1);
		}

		json.add(String.valueOf(slot), element);
	}

	private static JsonObject outputs(Recipe<?> recipe, HolderLookup.Provider registries) {
		JsonObject json = new JsonObject();
		ItemStack result = recipe.getResultItem(registries);

		if (!result.isEmpty()) {
			JsonObject stack = new JsonObject();
			ResourceLocation id = BuiltInRegistries.ITEM.getKey(result.getItem());
			stack.addProperty("item", id.toString());
			stack.addProperty("count", result.getCount());
			json.add("1", stack);
		}

		return json;
	}
}
