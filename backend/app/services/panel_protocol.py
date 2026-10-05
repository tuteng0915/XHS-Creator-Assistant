"""Small, versioned task adapter. Legacy snapshots never gain implicit task fields."""
from app.models import PanelTask

DISCUSSION_DISABLED_REASON = "本次只做独立试读，未开启互相回应。"


def panel_discussion_enabled(context: dict) -> bool:
    task = context.get("panelTask")
    return task is None or PanelTask.model_validate(task).discussion_enabled


def panel_prompt_context(topic: dict | None) -> str:
    raw = (topic or {}).get("panelTask")
    if raw is None:
        return ""
    task = PanelTask.model_validate(raw)
    mode = (
        "这是受邀的定向试读，请围绕 focusQuestions 给出自己的理解和疑问；"
        "回答是受邀反馈，不是假装自然发生的留言，问题中的判断也不必赞同。"
        if task.reading_mode == "guided" else
        "这是自然全文试读，不是专业文案评审；按自己的需要决定是否公开表达。"
    )
    return ("\n本次 panelTask 是试读协议，与 demo/live 无关。" + mode
            + "已经提供全文时不假称测试过只看标题的点开行为。"
            + ("互相回应已关闭，不把第二轮空结果视为缺失或沉默。"
               if not task.discussion_enabled else ""))
