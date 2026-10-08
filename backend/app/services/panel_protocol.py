"""Small, versioned task adapter. Legacy snapshots never gain implicit task fields."""
from app.models import PanelTask
from app.services.simulation_review import simulation_category

DISCUSSION_DISABLED_REASON = "本次只做独立试读，未开启互相回应。"


def panel_discussion_enabled(context: dict) -> bool:
    task = context.get("panelTask")
    return task is None or PanelTask.model_validate(task).discussion_enabled


def panel_prompt_context(topic: dict | None) -> str:
    category = simulation_category(topic)
    purpose = {
        "account": "这是账号级受众访谈：看多篇已提供的内容样本，谈为什么关注、希望持续看到什么，"
                   "可以不喜欢某些方向；不是修改一篇稿件，不把单篇样本说成账号全部内容。",
        "published_note": "这是已发布笔记的复盘：按这篇实际文字说理解、兴趣和阻力。"
                          "作者关心下一篇同类型内容怎么做，不要求修改或重发眼前这篇。"
                          "不把模拟感受声称为已证实的真实流量成因。",
        "creation": "",
    }[category]
    raw = (topic or {}).get("panelTask")
    if raw is None:
        return purpose
    task = PanelTask.model_validate(raw)
    mode = (
        "这是受邀的定向试读，请围绕 focusQuestions 给出自己的理解和疑问；"
        "回答是受邀反馈，不是假装自然发生的留言，问题中的判断也不必赞同。"
        if task.reading_mode == "guided" else
        "这是自然全文试读，不是专业文案评审；按自己的需要决定是否公开表达。"
    )
    concept = (topic or {}).get("previewLevel") == "concept"
    scope = ("当前提供多篇账号内容样本，围绕自己的关注需求表达期待。"
             if category == "account" else
             "当前只给了标题。这是选题意愿测试：说是否想看、你期待得到什么。"
             "不要反复批评正文缺失，不声称已读完整内容，不替标题补充院校、课程、数字或事实。"
             if concept else "当前提供的是正文试读：具体说哪句话吸引你、让你困惑或失去兴趣。")
    return ("\n本次 panelTask 是试读协议，与 demo/live 无关。" + purpose + mode + scope
            + "公开发言像群聊，通常一两句话；分析依据另放理解与疑问字段。"
            + "回复正文不要出现 messageId、personaId 或 @加内部编号；收件关系只用结构化字段表示。"
            + "与自己无关就可以划走，不因被选入就强行找到联系；不凭常识补项目属性或统计数字。"
            + "已经提供全文时不假称测试过只看标题的点开行为。"
            + ("互相回应已关闭，不把第二轮空结果视为缺失或沉默。"
               if not task.discussion_enabled else ""))
