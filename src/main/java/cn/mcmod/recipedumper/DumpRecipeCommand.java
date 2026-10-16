package cn.mcmod.recipedumper;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;

import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.HolderLookup;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.item.crafting.RecipeManager;

import net.neoforged.fml.loading.FMLPaths;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 配方导出的核心逻辑。
 *
 * <p>命令 {@code /dumprecipe <modid>} 和自动导出都走 {@link #dumpTo}，
 * 保证两条路子出来的文件完全一致。</p>
 */
public final class DumpRecipeCommand {
	/**
	 * 自动导出用的环境变量。
	 *
	 * <p>设了它（值是 modid）之后，服务端启动完成时会自动导出一次。
	 * 无人值守的环境里没法在控制台敲命令，靠这个做脚本化验证 / CI。
	 * 不设就什么都不发生。</p>
	 */
	public static final String AUTO_ENV = "RECIPEDUMPER_AUTO";

	private DumpRecipeCommand() {
	}

	public static int run(CommandContext<CommandSourceStack> context) {
		String modId = StringArgumentType.getString(context, "mod");
		CommandSourceStack source = context.getSource();

		try {
			int dumped = dumpTo(source.getServer(), modId);
			int skipped = lastSkipped;

			source.sendSuccess(() -> Component.literal(
					"Dump recipes successfully! See export Directory."), false);
			source.sendSuccess(() -> Component.literal(
					dumped + " recipes dumped, " + skipped + " recipes skipped"), false);
			return dumped;
		} catch (IOException exception) {
			source.sendFailure(Component.literal("写入文件失败: " + exception.getMessage()));
			return 0;
		}
	}

	/** 上一次导出里失败的条数，供命令反馈用。 */
	private static int lastSkipped;

	/**
	 * 把指定命名空间的配方导出到 {@code <游戏目录>/export/dump_recipes_<modid>.json}。
	 *
	 * @return 成功导出的条数
	 */
	public static int dumpTo(MinecraftServer server, String modId) throws IOException {
		RecipeManager recipeManager = server.getRecipeManager();
		HolderLookup.Provider registries = server.registryAccess();

		JsonArray recipes = new JsonArray();
		JsonArray errors = new JsonArray();

		for (RecipeHolder<?> holder : recipeManager.getRecipes()) {
			if (!holder.id().getNamespace().equals(modId)) {
				continue;
			}

			try {
				recipes.add(RecipeJson.toJson(holder, registries));
			} catch (Throwable throwable) {
				// 单条失败不影响整体，记下 id 继续
				errors.add(holder.id().toString());
				RecipeDumper.LOGGER.warn("[RecipeDumper] 导出失败: {}", holder.id(), throwable);
			}
		}

		JsonObject root = new JsonObject();
		root.add("recipes", recipes);
		root.add("error", errors);

		int dumped = recipes.size();
		lastSkipped = errors.size();

		Path dir = FMLPaths.GAMEDIR.get().resolve("export");
		Path file = dir.resolve("dump_recipes_" + modId + ".json");
		Files.createDirectories(dir);

		// disableHtmlEscaping：tag 之类的字符串里可能有 <、>，别被转义成 \u003c
		Gson gson = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
		Files.writeString(file, gson.toJson(root), StandardCharsets.UTF_8);

		RecipeDumper.LOGGER.info("[RecipeDumper] {} 条配方已导出到 {}（{} 条失败）",
				dumped, file, lastSkipped);

		return dumped;
	}
}
