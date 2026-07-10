"""
Haiku + Sonnet 混搭分块请求
Phase 1: Haiku 并行 (Profile + PainPoints) → ~3-5s
Phase 2: Sonnet (Topics+Titles)            → ~15s
Phase 3: Sonnet (Structure)                → ~12s
用法: python3 test_prompt.py
"""
import sys, json, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, '/Users/tut/Library/Python/3.9/lib/python/site-packages')
import anthropic

KEY_FILE = "key"
HAIKU   = "claude-haiku-4-5-20251001"
SONNET  = "claude-sonnet-4-6"

# ── 样本输入 ──────────────────────────────────────────────
POSITIONING = """账号:@QSheep｜留学内容创作者,1.4K 粉。核心人群=正在准备/纠结出国读研的文科生(传媒、社科、人类学),目标英港新前30。
内容主张:真实反思 + 决策方法,不贩卖焦虑、不灌鸡汤。
作者优势:亲历者视角、擅长把模糊焦虑拆成可执行的决策步骤、文笔好。"""

NOTES = """二本逆袭G5?别再被这种标题骗了 ｜ 赞1.4k 藏980 ｜ 爆
留学中介到底值不值5万块|我的真实账单与避坑清单 ｜ 赞1.1k 藏860 ｜ 爆
选校时我后悔没早知道的6件事 ｜ 赞720 藏610 ｜ 爆
文科留学回国到底有没有用|工作一年后说点实话 ｜ 赞90 藏40 ｜ 平
DIY申请时间线:从大三暑假到递交我每个月都干了啥 ｜ 赞60 藏150 ｜ 差"""

COMMENTS = """中介那部分太真实了,我现在就纠结要不要DIY,自己怕搞砸
想问下双非背景冲英国前30有戏吗,真的好焦虑
回国后发现海归学历根本不值钱,有点后悔
求一个选校时间线!完全不知道几月该干嘛,好慌
文书到底自己写还是找人改啊,我憋了两周写不出来
家里不太支持留学,该怎么说服父母
雅思一直卡6.5,是不是该先把雅思考完再准备申请
想知道港三和英国前30到底怎么选,纠结死了
均分85冲刺前20稳吗,GPA算是劣势吗
看了好多博主都在贩卖焦虑,终于有人好好说话了
转专业申请会不会很吃亏,本科传媒想转社科
预算有限,中介和DIY的钱到底该花在哪一步
实习经历很水,文书里要不要硬写
拿到offer了但突然不确定该不该去,好迷茫"""

# ── 4 段集中 Prompt ───────────────────────────────────────

PROMPT_PROFILE = """你是创作者账号分析师。基于历史笔记和账号定位，分析这个账号的爆款基因。
规则：
- pillars 每条 10 字以内，概括性词组，不加冒号或括号展开
- 若笔记含数据（格式「标题｜数据｜爆/平/差」），必须提供 contrast 对比诊断
- winFactors/loseFactors/takeaways 落到选题类型/标题变量/内容形态，不泛泛而谈
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"profile":{"pillars":[],"titleFormulas":[{"formula":"","examples":[]}],"hookStyles":[],"viralStructure":{"name":"","steps":[]},"voiceFingerprint":[],"contrast":{"winners":[{"title":"","metric":""}],"losers":[{"title":"","metric":""}],"winFactors":[],"loseFactors":[],"takeaways":[]}}}"""

PROMPT_PAIN_POINTS = """你是评论区分析师。聚合评论区原文，提炼 3~5 个读者痛点主题，每个带原文证据。
排序规则：intensity 高→中，同级按 count 降序。
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"painPoints":[{"theme":"","intensity":"高/中","count":0,"evidence":[]}]}"""

PROMPT_TOPICS = """你是内容选题策略师。基于账号定位、爆款基因诊断和评论区痛点，生成 3~4 个选题 + 2 组标题变体。
重要约束：
① topics[0] 必须对应 painPoints[0]（最高频/最高强度痛点），直接命中它
② 每个 whyFit 必须结合账号的惯用结构和风格指纹，不能是通用表述
③ titles 选 topics[0] 和 topics[1] 各给 3 条变体，贴合已归纳的标题公式，不贩卖焦虑
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"topics":[{"title":"","angle":"","pain":"","whyFit":""}],"titles":[{"topic":"","variants":[]}]}"""

PROMPT_STRUCTURE = """你是内容结构师。为指定选题写完整笔记骨架，并提炼可跨选题复用的表达结构。
重要：topicChosen 必须与输入的「选题」原文完全一致。
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"structure":{"topicChosen":"","outline":[{"sec":"","ct":""}],"reuse":""}}"""


def parse_json(raw: str):
    txt = re.sub(r'```json|```', '', raw).strip()
    fi, fa = txt.find('{'), txt.find('[')
    if fa != -1 and (fi == -1 or fa < fi):
        return json.loads(txt[fa: txt.rfind(']') + 1])
    return json.loads(txt[fi: txt.rfind('}') + 1])


def call_chunk(client, model: str, system: str, user: str, max_tokens: int, label: str):
    t0 = time.time()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    elapsed = time.time() - t0
    data = parse_json(msg.content[0].text)
    print(f"  [{label:<22}] {elapsed:5.1f}s | {msg.usage.output_tokens:4d} tok | {model.split('-')[1]}")
    return data


def run():
    key = open(KEY_FILE).read().strip()
    client = anthropic.Anthropic(api_key=key)

    print(f"=== Haiku+Sonnet 混搭分块 ===\n")
    total_t0 = time.time()

    # ── Phase 1: 真并行 (ThreadPoolExecutor) ──────────────
    print("Phase 1 · Haiku 并行 (① Profile + ② PainPoints):")
    phase1_t0 = time.time()

    profile, painPoints = None, None

    def fetch_profile():
        return call_chunk(client, HAIKU, PROMPT_PROFILE,
            f"【账号定位】\n{POSITIONING}\n\n【历史/对标笔记】\n{NOTES}", 2000, "① Profile")

    def fetch_pain_points():
        return call_chunk(client, HAIKU, PROMPT_PAIN_POINTS,
            f"【评论区原文】\n{COMMENTS}", 800, "② PainPoints")

    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(fetch_profile): 'profile', ex.submit(fetch_pain_points): 'pain'}
        for f in as_completed(futures):
            key_name = futures[f]
            result = f.result()
            if key_name == 'profile':
                profile = result['profile']
            else:
                painPoints = result['painPoints']

    phase1_elapsed = time.time() - phase1_t0
    print(f"  Phase 1 实际并行耗时: {phase1_elapsed:.1f}s\n")

    # ── Phase 2: Sonnet · Topics + Titles ─────────────────
    print("Phase 2 · Sonnet (③ Topics + Titles):")
    topics_data = call_chunk(client, SONNET, PROMPT_TOPICS,
        f"【账号定位】\n{POSITIONING}\n\n"
        f"【爆款基因】\n{json.dumps({'profile': profile}, ensure_ascii=False)}\n\n"
        f"【痛点】\n{json.dumps({'painPoints': painPoints}, ensure_ascii=False)}",
        2000, "③ Topics+Titles")
    topics = topics_data['topics']
    titles = topics_data['titles']
    print()

    # ── Phase 3: Sonnet · Structure ───────────────────────
    print("Phase 3 · Sonnet (④ Structure):")
    chosen = topics[0]['title'] if topics else ''
    struct_data = call_chunk(client, SONNET, PROMPT_STRUCTURE,
        f"【账号定位】\n{POSITIONING}\n\n"
        f"【风格指纹】\n{'；'.join(profile.get('voiceFingerprint', []))}\n\n"
        f"【爆款结构】\n{profile.get('viralStructure', {}).get('name', '')}\n\n"
        f"【选题】\n{chosen}",
        1500, "④ Structure")
    structure = struct_data['structure']

    total_elapsed = time.time() - total_t0
    print(f"\n总耗时: {total_elapsed:.1f}s")
    print(f"  Phase1={phase1_elapsed:.1f}s (并行) + Phase2+3={total_elapsed - phase1_elapsed:.1f}s (串行)\n")

    # ── 打印结果 ──────────────────────────────────────────
    print("═" * 60)
    print("① 内容支柱:", ' | '.join(profile.get('pillars', [])))

    print("\n① 标题公式")
    for f in profile.get('titleFormulas', []):
        print(f"  {f['formula']}")
        for ex in f.get('examples', []):
            print(f"    例: {ex}")

    print("\n① takeaways")
    for t in profile.get('contrast', {}).get('takeaways', []):
        print(f"  → {t}")

    print("\n② 痛点")
    for pp in painPoints:
        print(f"  [{pp['intensity']}] {pp['theme']} ({pp['count']}条)")

    print("\n③ 选题 (topics[0] 应对应 painPoints[0])")
    for i, t in enumerate(topics):
        marker = "← topics[0]" if i == 0 else ""
        print(f"  {i}. {t['title']} {marker}")

    print("\n③ 标题变体")
    for t in titles:
        print(f"  [{t['topic'][:30]}...]")
        for i, v in enumerate(t['variants']):
            print(f"    {chr(65+i)}. {v}")

    print("\n④ 结构")
    print(f"  topicChosen: {structure['topicChosen']}")
    for o in structure.get('outline', []):
        print(f"  [{o['sec']}] {o['ct'][:60]}...")
    print(f"\n  复用: {structure.get('reuse', '')[:80]}...")

    # 保存
    full = {'profile': profile, 'painPoints': painPoints,
            'topics': topics, 'titles': titles, 'structure': structure}
    with open("live_output_chunked.json", "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 保存至 live_output_chunked.json")


if __name__ == "__main__":
    run()
