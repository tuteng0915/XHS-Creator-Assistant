"""Authored teaching examples, NOT observations about the current account.

Design sources and adaptation limits: docs/audience-simulation-methods.md.
Proxona (CHI 2025) motivates needs/unknowns; Writer-Defined AI Personas
(CHI 2024, §3.3.2) motivates explicit input/output demonstrations.
These examples teach a method, not population frequencies or optimal labels.
"""

ANALYSIS_EXAMPLES = """
以下是人工编写的教学示例，不是当前账号数据。不得引用示例的内容或虚构其来源 ID。
输入：笔记介绍留学费用；评论“住宿和保险算进去了吗？”
输出示范：需求为费用口径完整，依据为该追问；收入、家庭条件未知，不能推断低收入。
输入：笔记介绍申请路线；评论“非应届也能用吗？”
输出示范：需求为适用条件明确；是否已经毕业未知，提问不等于本人身份。
输入：评论“蹲蹲”。
输出示范：具体需求未知，不能凭这一句独立建立预算敏感或申请焦虑画像。
输入：笔记标题“非应届申请步骤”，正文列出时间线和材料清单；没有采集到评论。
输出示范：可提出“可能需要非应届申请步骤的读者”作为内容推断视角，引用笔记原文；不能称该群体已在评论中出现，也不能推断其年龄、职业或人数。
输入：评论询问“房源还有吗？”或“价格多少？”。
输出示范：可归纳为“需要房源可用性或价格信息”的视角；不能据此断言评论者已经入学、预算紧张或即将成交。
输入：同篇有“步骤清楚”和“我的情况用不上”。
输出示范：需求可重叠，分别保留有帮助与适用性异议，不用一个人物故事抹去分歧。
以上仅教分析方法。接下来只引用用户输入中的真实笔记和评论。
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
