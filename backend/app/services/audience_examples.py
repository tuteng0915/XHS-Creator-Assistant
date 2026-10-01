"""Authored teaching examples, NOT observations about the current account.

Design sources and adaptation limits: docs/audience-simulation-methods.md.
Proxona (CHI 2025) motivates needs/unknowns; Writer-Defined AI Personas
(CHI 2024, §3.3.2) motivates explicit input/output demonstrations.
These examples teach a method, not population frequencies or optimal labels.
"""

ANALYSIS_EXAMPLES = """
以下是人工编写的教学示例，不是当前账号数据。不得引用示例的内容或虚构其来源 ID。
输入：笔记分享申请准备清单和费用；评论有“住宿和保险算进去了吗？”、“想试但怕来不及”、“先收藏”。
简短角色示范（此处只演示三位，实际优先给 8 位）：
1. name=较真核算派；profile=习惯把账算清楚再决定，遇到笼统结论会追问；
coreConcern=费用是否包含住宿和保险；contentPreference=分项账单；
expressionStyle=冷静短句，追问数字。关注点可引用费用评论。
2. name=心动行动派；profile=容易被机会吸引，想尽快知道从哪里开始；
coreConcern=现在开始是否还来得及；contentPreference=第一步与时间线；
expressionStyle=热情直接，连着提问。关注点可引用“想试但怕来不及”。
3. name=安静收藏派；profile=先把有用的信息存起来，通常不急着表态；
coreConcern=以后能否照着清单准备；contentPreference=便于回看的步骤；
expressionStyle=多看少说，偶尔问关键细节。关注点可引用准备清单和“先收藏”。
这三种性格是用于模拟的设定；不据此断言评论者的收入、身份或真实人格。接下来按这个简短粒度生成当前账号的角色，只引用当前输入中的真实笔记和评论。
"""

REACTION_EXAMPLES = """
以下为人工编写的阅读反应示范，不是真实历史案例，不代表动作概率，不要照抄。
输入：视角关注费用口径；待测正文“每月生活费五千，不含住宿”。
输出示范：understanding=五千不包含住宿；triggerQuote=不含住宿；
action=comment；quote=住宿大约还要准备多少？；stance=犹豫。
输入：视角关心适用条件；正文“以下只适用于应届生”；自身是否应届未知。
输出示范：understanding=建议有明确适用范围；triggerQuote=只适用于应届生；
action=no_comment；quote=空字符串；stance=不确定。不能替角色补造毕业经历。
真实 observedEpisodes 是历史内容与评论的配对，不是本次作品的反馈；
同一需求可以产生不同反应，不要把历史评论原句复制到新作品，不要将案例条数当人数。
"""
