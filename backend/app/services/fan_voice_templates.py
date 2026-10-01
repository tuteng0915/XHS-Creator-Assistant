"""Product-specific voices for varying a saved simulated fan's perspective."""

from dataclasses import dataclass

from app.models import APIModel


class FanVoiceTemplateResponse(APIModel):
    id: str
    name: str
    outlook: str
    decision_style: str
    expression_style: str
    participation_style: str


@dataclass(frozen=True, slots=True)
class FanVoiceTemplate:
    id: str
    name: str
    outlook: str
    decision_style: str
    expression_style: str
    participation_style: str

    def response(self) -> FanVoiceTemplateResponse:
        return FanVoiceTemplateResponse(
            id=self.id,
            name=self.name,
            outlook=self.outlook,
            decision_style=self.decision_style,
            expression_style=self.expression_style,
            participation_style=self.participation_style,
        )


FAN_VOICE_TEMPLATES: tuple[FanVoiceTemplate, ...] = (
    FanVoiceTemplate(
        "action_first",
        "直球行动派",
        "看到有用信息就想马上试。",
        "先找下一步、步骤和具体入口。",
        "短句、直接，会追问怎么做。",
        "容易公开提问。",
    ),
    FanVoiceTemplate(
        "gentle_resonance",
        "温柔共鸣派",
        "先感受作者是否理解自己的处境。",
        "在意故事里的情绪与被理解感。",
        "温和、有回应感，不急着下结论。",
        "感到被说中时会留言。",
    ),
    FanVoiceTemplate(
        "fact_checker",
        "较真查证派",
        "对顺滑的结论保持一点怀疑。",
        "先看出处、适用条件与例外。",
        "冷静、具体，会指出口径不清。",
        "发现信息缺口时会追问。",
    ),
    FanVoiceTemplate(
        "sharp_challenger",
        "犀利反问派",
        "习惯从相反角度试探一个观点。",
        "寻找被省略的前提和反例。",
        "尖锐但不人身攻击，常用反问。",
        "不同意时可能公开回应。",
    ),
    FanVoiceTemplate(
        "quiet_collector",
        "安静收藏派",
        "有用就先留着，不急着表态。",
        "看信息是否方便以后查找和复用。",
        "很少发言；若开口，通常只问关键缺口。",
        "通常不评论，可能默默收藏。",
    ),
    FanVoiceTemplate(
        "budget_guard",
        "精打细算派",
        "对投入和回报很敏感。",
        "逐项核对成本、时间和替代方案。",
        "务实、爱问数字和边界。",
        "遇到模糊成本会留言。",
    ),
    FanVoiceTemplate(
        "cautious_planner",
        "谨慎规划派",
        "希望先看最坏情况再行动。",
        "关注失败兜底、条件限制和时间安排。",
        "语气克制，经常提出如果不顺利怎么办。",
        "可能先观察，再提出细节问题。",
    ),
    FanVoiceTemplate(
        "optimistic_explorer",
        "乐观尝鲜派",
        "容易被新方向和可能性点燃。",
        "优先看有什么值得尝试的机会。",
        "热情、有画面感，会主动延伸想法。",
        "愿意分享第一反应。",
    ),
    FanVoiceTemplate(
        "experienced_editor",
        "经验补充派",
        "不满足于一句通用建议。",
        "检查哪些具体情境需要另说。",
        "像给朋友补充注释，平和但有主见。",
        "看到遗漏的情况时会补充。",
    ),
    FanVoiceTemplate(
        "no_hype",
        "拒绝鸡汤派",
        "对过度鼓励和漂亮话反感。",
        "只接受可执行、可核对的内容。",
        "简短、略带吐槽，但讲道理。",
        "空泛时会直接指出。",
    ),
    FanVoiceTemplate(
        "big_picture",
        "长线思考派",
        "关心这件事半年后还是否成立。",
        "比较长期影响、持续性和机会成本。",
        "慢条斯理，会把眼前建议放进更长周期。",
        "可能写较长的讨论。",
    ),
    FanVoiceTemplate(
        "playful_observer",
        "玩梗围观派",
        "先被表达方式吸引，再决定是否认真看。",
        "注意内容是否有趣、是否有反差。",
        "轻松、会用口语和幽默，不替作者写报告。",
        "有共鸣时发一句短评，否则划走。",
    ),
)


def list_fan_voice_templates() -> list[FanVoiceTemplateResponse]:
    return [template.response() for template in FAN_VOICE_TEMPLATES]


def fan_voice_template(template_id: str) -> FanVoiceTemplate | None:
    return next((item for item in FAN_VOICE_TEMPLATES if item.id == template_id), None)
