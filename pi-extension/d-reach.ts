/**
 * d-reach 插件版（与 skill 并行，不替代）
 *
 * skill 版靠 agent 读 SKILL.md 自己拼命令；这个插件把同一套通道变成 pi 原生工具，
 * 由模型直接调用，并且多一层「分级」：quick / base / deep 三档按需选路。
 *
 * 工具
 *   d_reach        跑一轮检索，返回精简摘要 + 结构化 details（完整结果落盘）
 *   d_reach_state  通道健康 + 额度（读 channels.json / quota.json）
 *
 * 命令
 *   /reach <query>        等价于 d_reach 的 base 档，结果只弹通知
 *   /reach-deep <query>   deep 档
 *
 * 后端仍然是 skill 里的 scripts/fanout.sh —— 这个插件只是多一个入口，不复制逻辑。
 */

import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

const run = promisify(execFile);
const SKILL_DIR = join(homedir(), ".agents/skills/d-reach");
const FANOUT = join(SKILL_DIR, "scripts/fanout.sh");
const DATA_DIR = join(homedir(), ".agent-reach");
const LAST_RUN = join(DATA_DIR, "last-run.md");

/** 分级：quick 只打 3 路互补通道，省时间省额度 */
const PROFILES = {
	auto: { label: "auto · 按意图选 3 路", on: "" },
	quick: { label: "quick · 3 路固定", on: "qianfan,fcdev,tf" },
	base: { label: "base · 9 路", on: "" },
	deep: { label: "deep · 13 路", on: "" },
} as const;

/**
 * 按 query 特征选通道（真·意图路由）。
 * 只挑 2-4 路，剩下的交给 base/deep 档；命中不准时用 channels 参数覆盖。
 */
function pickByIntent(query: string): { on: string; why: string } {
	const zh = /[\u4e00-\u9fff]/.test(query);
	const paper = /(paper|arxiv|论文|文献|survey|benchmark|sota|研究综述)/i.test(query);
	const news = /(最新|今天|昨天|本周|发布|上线|价格|股价|行情|release|changelog|202[5-9])/i.test(query);
	const code = /(error|exception|traceback|stack ?trace|compile|build|报错|编译|部署|配置|安装|依赖|函数)/i.test(query);
	// 中文 query 里夹的英文技术词，判断"中文技术"而不是"中文通用"
	const tech = /\b(mtu|wireguard|docker|k8s|kubernetes|python|java|rust|golang|node|api|sdk|http|tcp|udp|sql|git|nginx|redis|kafka|postgres|mysql|linux|bug|fix)\b/i.test(query);

	if (paper) return { on: "oalex,crossref,fcres", why: "学术：OpenAlex + Crossref + Research Index" };
	if (news) return { on: "langsearch,tf,qianfan", why: "时效：LangSearch + TinyFish + 千帆" };
	if (zh && (code || tech)) return { on: "qianfan,se,jj", why: "中文技术：千帆 + StackExchange + 掘金" };
	if (zh) return { on: "qianfan,jj,segfault", why: "中文通用：千帆 + 掘金 + SegmentFault" };
	if (code || tech) return { on: "se,fcdev,tf", why: "英文技术：StackExchange + Firecrawl Dev + TinyFish" };

	return { on: "tf,fcdev,qianfan", why: "通用兜底：TinyFish + Firecrawl Dev + 千帆" };
}

type Profile = keyof typeof PROFILES;

interface Hit {
	title: string;
	url: string;
	note: string;
}

interface ChannelResult {
	key: string;
	name: string;
	mark: string;
	status: "ok" | "zero" | "fail" | "skip";
	note: string;
	hits: Hit[];
}

interface Parsed {
	channels: ChannelResult[];
	summary: string;
	next: string;
	health: string;
}

const MARK_STATUS: Record<string, ChannelResult["status"]> = {
	"✅": "ok",
	"💬": "ok",
	"⚪": "zero",
	"❌": "fail",
	"⚠️": "fail",
	"🔇": "skip",
};

/** 把 fanout.sh 的 markdown 解析成结构；解析不了就退化成空列表，不抛错 */
function parseFanout(md: string): Parsed {
	const channels: ChannelResult[] = [];
	let cur: ChannelResult | null = null;
	let summary = "";
	let next = "";
	let health = "";

	for (const raw of md.split("\n")) {
		const line = raw.trimEnd();

		const head = line.match(/^###\s+(✅|⚪|❌|⚠️|🔇|💬)\s+(.+)$/);
		if (head) {
			const mark = head[1];
			let rest = head[2];
			let note = "";
			const dash = rest.match(/^(.*?)\s*——\s*(.+)$/);
			if (dash) {
				rest = dash[1];
				note = dash[2];
			}
			cur = {
				key: "",
				name: rest.trim(),
				mark,
				status: MARK_STATUS[mark] ?? "zero",
				note,
				hits: [],
			};
			channels.push(cur);
			continue;
		}

		if (line.startsWith("**汇总**")) {
			summary = line.replace(/^\*\*汇总\*\*：/, "").replace(/\*\*/g, "").trim();
			cur = null;
			continue;
		}
		if (line.startsWith("**通道健康**")) {
			health = line.replace(/^\*\*通道健康\*\*：/, "").replace(/\*\*/g, "").trim();
			continue;
		}
		if (line.startsWith("**下一步**")) {
			next = line.replace(/^\*\*下一步\*\*：/, "").replace(/\*\*/g, "").trim();
			cur = null;
			continue;
		}

		if (cur) {
			const item = line.match(/^-\s+\[(.+?)\]\((.+?)\)(?:\s+—\s+(.*))?$/);
			if (item) {
				cur.hits.push({ title: item[1], url: item[2], note: (item[3] ?? "").trim() });
				continue;
			}
			const plain = line.match(/^-\s+(.+)$/);
			if (plain) cur.hits.push({ title: plain[1], url: "", note: "" });
		}
	}

	return { channels, summary, next, health };
}

/** 模型看到的文本：只给状态 + 每路前 N 条，避免一次灌几千字 */
function brief(parsed: Parsed, perChannel: number): string {
	const lines: string[] = [];
	for (const ch of parsed.channels) {
		const state =
			ch.mark === "💬"
				? "AI 摘要（非来源，可当线索）"
				: ch.status === "ok"
				? `${ch.hits.length} 条`
				: ch.status === "zero"
					? "0 命中"
					: ch.status === "skip"
						? `跳过${ch.note ? `（${ch.note}）` : ""}`
						: `失败${ch.note ? `（${ch.note}）` : ""}`;
		lines.push(`- ${ch.name}：${state}`);
		for (const hit of ch.hits.slice(0, perChannel)) {
			lines.push(`  · ${hit.title}${hit.url ? ` — ${hit.url}` : ""}`);
		}
	}
	if (parsed.summary) lines.push("", `汇总：${parsed.summary}`);
	if (parsed.health) lines.push(`通道健康：${parsed.health}`);
	return lines.join("\n");
}

async function runFanout(
	query: string,
	profile: Profile,
	channels: string,
): Promise<{ md: string; secs: number; on: string; why: string }> {
	const args = [FANOUT, query];
	if (profile === "deep") args.push("--deep");
	let why = "";
	let on = channels || PROFILES[profile].on;
	if (!on && profile === "auto") {
		const picked = pickByIntent(query);
		on = picked.on;
		why = picked.why;
	}
	if (on) args.push("--on", on);

	const t0 = Date.now();
	const { stdout } = await run("bash", args, { timeout: 200_000, maxBuffer: 8 << 20 });
	return { md: stdout, secs: (Date.now() - t0) / 1000, on, why };
}

async function persist(md: string, query: string): Promise<string> {
	await mkdir(DATA_DIR, { recursive: true });
	await writeFile(LAST_RUN, `<!-- ${query} -->\n${md}`, "utf8");
	return LAST_RUN;
}

const searchTool = defineTool({
	name: "d_reach",
	label: "d-reach 检索",
	description:
		"多通道并发检索：中文走百度千帆、代码走 Firecrawl/StackExchange、通用走 TinyFish/LangSearch。" +
		"profile=quick 只打 3 路（约 4s，适合点查）；base 9 路（约 6s）；deep 13 路含限额通道（约 12s）。" +
		"返回精简摘要，完整来源已存到 details.file。",
	parameters: Type.Object({
		query: Type.String({ description: "检索词，中英文均可" }),
		profile: Type.Optional(
			Type.Union(
				[
					Type.Literal("auto"),
					Type.Literal("quick"),
					Type.Literal("base"),
					Type.Literal("deep"),
				],
				{
					description:
						"auto=按 query 意图自动选 3 路（默认推荐）；quick=固定 3 路；base=9 路；deep=13 路含限额通道",
				},
			),
		),
		channels: Type.Optional(
			Type.String({ description: "显式指定通道，逗号分隔，如 hn,exa；会覆盖 profile 的路由" }),
		),
	}),

	async execute(_id, params, _signal, _onUpdate, _ctx) {
		const query = params.query.trim();
		if (!query) {
			return { content: [{ type: "text", text: "query 不能为空" }], isError: true };
		}
		const profile = (params.profile ?? "auto") as Profile;
		try {
			const { md, secs, on, why } = await runFanout(query, profile, params.channels ?? "");
			const parsed = parseFanout(md);
			const file = await persist(md, query);
			const perChannel = profile === "quick" ? 3 : 2;
			const text = [
				`d-reach ${PROFILES[profile].label} · ${secs.toFixed(1)}s` +
					(why ? ` · ${why}` : on ? ` · ${on}` : ""),
				brief(parsed, perChannel),
				"",
				`完整结果（含全部来源与原因）：${file}`,
			].join("\n");
			return {
				content: [{ type: "text", text }],
				details: {
					query,
					profile,
					secs,
					file,
					summary: parsed.summary,
					channels: parsed.channels.map((c) => ({
						name: c.name,
						mark: c.mark,
						status: c.status,
						note: c.note,
						count: c.hits.length,
					})),
				},
			};
		} catch (err) {
			const msg = err instanceof Error ? err.message : String(err);
			return {
				content: [{ type: "text", text: `d-reach 执行失败：${msg.slice(0, 300)}` }],
				isError: true,
			};
		}
	},
});

const stateTool = defineTool({
	name: "d_reach_state",
	label: "d-reach 状态",
	description: "看各通道健康（连败次数、最后成功）与限额通道已用/上限，判断这轮还能不能铺满。",
	parameters: Type.Object({}),

	async execute() {
		const readJson = async (p: string) => {
			try {
				return JSON.parse(await readFile(p, "utf8")) as Record<string, unknown>;
			} catch {
				return {};
			}
		};
		const health = await readJson(join(DATA_DIR, "channels.json"));
		const quota = await readJson(join(DATA_DIR, "quota.json"));
		const official = (quota._official ?? {}) as Record<string, { state?: string; remaining?: number; total?: number; balance?: string; currency?: string }>;

		const lines: string[] = ["通道健康："];
		const bad = Object.entries(health)
			.filter(([, v]) => ((v as { streak_fail?: number }).streak_fail ?? 0) >= 3)
			.map(([k]) => k);
		lines.push(bad.length ? `  连败 ≥3（下轮自动跳过）：${bad.join(", ")}` : "  没有通道被拉黑");

		lines.push("", "限额通道：");
		for (const [svc, v] of Object.entries(quota)) {
			if (svc.startsWith("_") || typeof v !== "object" || v === null) continue;
			const used = (v as { monthly?: number }).monthly ?? 0;
			const off = official[svc];
			const tail =
				off?.state === "ok" && svc === "firecrawl"
					? ` | 官方剩余 ${off.remaining}/${off.total}`
					: off?.state === "ok" && svc === "tinyfish"
						? ` | 钱包 ${off.balance} ${off.currency}`
						: off?.state === "unavailable" || off?.state === "no_permission"
							? " | 官方查不到"
							: "";
			lines.push(`  ${svc}: 本月已用 ${used}${tail}`);
		}
		return { content: [{ type: "text", text: lines.join("\n") }], details: { health, quota } };
	},
});

export default function dReachExtension(pi: ExtensionAPI) {
	pi.registerTool(searchTool);
	pi.registerTool(stateTool);

	pi.registerCommand("reach", {
		description: "d-reach 检索（base 档 9 路）",
		handler: async (args, ctx) => {
			const query = args.trim();
			if (!query) return ctx.ui.notify("用法：/reach <检索词>", "warning");
			ctx.ui.notify(`d-reach 检索中：${query}`, "info");
			try {
				const { md, secs } = await runFanout(query, "base", "");
				const parsed = parseFanout(md);
				await persist(md, query);
				ctx.ui.notify(`完成 ${secs.toFixed(1)}s · ${parsed.summary || "见 last-run.md"}`, "info");
			} catch (err) {
				ctx.ui.notify(`失败：${err instanceof Error ? err.message : String(err)}`, "error");
			}
		},
	});

	pi.registerCommand("reach-deep", {
		description: "d-reach 检索（deep 档 13 路）",
		handler: async (args, ctx) => {
			const query = args.trim();
			if (!query) return ctx.ui.notify("用法：/reach-deep <检索词>", "warning");
			ctx.ui.notify(`d-reach deep 检索中：${query}`, "info");
			try {
				const { md, secs } = await runFanout(query, "deep", "");
				const parsed = parseFanout(md);
				await persist(md, query);
				ctx.ui.notify(`完成 ${secs.toFixed(1)}s · ${parsed.summary || "见 last-run.md"}`, "info");
			} catch (err) {
				ctx.ui.notify(`失败：${err instanceof Error ? err.message : String(err)}`, "error");
			}
		},
	});
}
