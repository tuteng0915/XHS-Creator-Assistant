"""Authored teaching examples, NOT observations about the current account.

Design sources and adaptation limits: docs/audience-simulation-methods.md.
Proxona (CHI 2025) motivates needs/unknowns; Writer-Defined AI Personas
(CHI 2024, §3.3.2) motivates explicit input/output demonstrations.
These examples teach a method, not population frequencies or optimal labels.
"""

ANALYSIS_EXAMPLES = """
以下是人工编写的教学示例，不是当前账号数据。不得引用示例的内容或虚构其来源 ID。
输入：笔记分享申请准备清单和费用；评论有“住宿和保险算进去了吗？”、“想试但怕来不及”、“先收藏”。
简短角色示范（此处只演示四位，实际优先给 8 位）：
1. name=较真核算派；interests=[留学,个人成长]；
profile=看到诱人的建议先核对总成本，漏项没说清就不急着决定；
coreConcern=想知道付出是否在可承受范围内；contentPreference=分项账单和方案对比；
expressionStyle=冷静短句，追问遗漏。需求可引用费用评论，不把“某项保险价格”固化为长期兴趣。
2. name=心动行动派；interests=[留学,个人成长]；
profile=看到机会想先试，准备太复杂就找一个今天能做的小步骤；
coreConcern=想拿到今天就能开始的第一步；contentPreference=短清单与操作示范；
expressionStyle=直奔操作，连着追问。需求可引用“想试但怕来不及”。
3. name=共鸣蓄力派；interests=[留学,个人成长]；
profile=被催进度时先退缩，看到坦诚的弯路分享才愿意继续准备；
coreConcern=想确认进度慢也还有选择；contentPreference=真实过程与不顺利的经历；
expressionStyle=先表达感受，再问能否缓一缓。也可用“想试但怕来不及”作为需求线索。
4. name=安静收藏派；interests=[留学,个人成长]；
profile=见到清晰清单先收好，要用时再逐项核对，很少公开表态；
coreConcern=想在需要时快速找到准备步骤；contentPreference=能直接回查的清单；
expressionStyle=多看少说，缺关键步骤才问。需求可引用准备清单和“先收藏”。
第二、三位是同一条模糊线索下的两种模拟可能：一位想尽快行动，一位先要安心，不说评论者一定是哪位。这些人的宽兴趣可以相同，差异在具体需要和遇事怎么反应，不只在语气。
反例：把人命名为“某学校保险咨询者”，简介写“理性谨慎，关注实用信息”，既兴趣过窄又行为含糊。也不要照抄这四种人到所有账号：做饭、运动或生活记录等内容应重新归纳自己的兴趣与需求。
另一个反例：作者回复“投到我的邮箱，越早越好”，不说明读者会催促别人投递。
读者问“接一对一指导吗”，可以提出“卡住时喜欢找人拆解问题”的角色；
同样关注“职业发展、个人成长”的另一位，可以“先自己试，失败后才带具体问题求助”。
前者需要及时反馈，后者需要自行排查的步骤，不替任何人补写付费意愿或已有工作经历。
这四种性格是用于模拟的设定；不据此断言评论者的收入、身份或真实人格。接下来按这个简短粒度生成当前账号的角色，只引用当前输入中的真实笔记和评论。
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
triggerQuote 只取一段连续短原文，不自行加入省略号拼接；多段意思留给 understanding 归纳。
"""
