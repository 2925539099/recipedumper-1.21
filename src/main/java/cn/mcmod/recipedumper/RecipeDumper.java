package cn.mcmod.recipedumper;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;

import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.SharedSuggestionProvider;

import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.ModList;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.server.ServerStartedEvent;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;

/**
 * 合成表导出（RecipeDumper）—— 为 MC百科导出配方的 NeoForge 版本。
 *
 * <p>原版 RecipeDumper 由 youyihj 制作、只做到 1.20.6，这里用 1.21.1 的配方 API 重写，
 * <strong>导出的 JSON 格式与原版保持一致</strong>，这样 MC百科那边才认得。</p>
 *
 * <h2>用法</h2>
 * <p>在游戏里执行 {@code /dumprecipe <modid>}（单人游戏需开启作弊），结果写到
 * {@code <游戏目录>/export/dump_recipes_<modid>.json}。</p>
 *
 * <p>无人值守时可以用环境变量 {@code RECIPEDUMPER_AUTO=<modid>} 让服务端启动后自动导出一次。</p>
 */
@Mod(RecipeDumper.MOD_ID)
public final class RecipeDumper {
	public static final String MOD_ID = "recipedumper";
	public static final Logger LOGGER = LoggerFactory.getLogger("RecipeDumper");

	public RecipeDumper(IEventBus modEventBus, ModContainer modContainer) {
		NeoForge.EVENT_BUS.addListener(RecipeDumper::onRegisterCommands);
		NeoForge.EVENT_BUS.addListener(RecipeDumper::onServerStarted);
	}

	private static void onRegisterCommands(RegisterCommandsEvent event) {
		CommandDispatcher<CommandSourceStack> dispatcher = event.getDispatcher();

		dispatcher.register(Commands.literal("dumprecipe")
				.then(Commands.argument("mod", StringArgumentType.word())
						// modid 补全：把所有已加载模组的 id 列出来
						.suggests((context, builder) -> SharedSuggestionProvider.suggest(
								ModList.get().getMods().stream().map(info -> info.getModId()).toList(),
								builder))
						.executes(DumpRecipeCommand::run)));
	}

	/** 环境变量触发的自动导出，方便脚本化验证。没设就什么都不做。 */
	private static void onServerStarted(ServerStartedEvent event) {
		String modId = System.getenv(DumpRecipeCommand.AUTO_ENV);

		if (modId == null || modId.isBlank()) {
			return;
		}

		try {
			int dumped = DumpRecipeCommand.dumpTo(event.getServer(), modId.trim());
			LOGGER.info("[RecipeDumper] 自动导出完成：{} 条配方（{}={}）",
					dumped, DumpRecipeCommand.AUTO_ENV, modId);
		} catch (IOException exception) {
			LOGGER.error("[RecipeDumper] 自动导出失败", exception);
		}
	}
}
