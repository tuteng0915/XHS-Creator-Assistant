# ruff: noqa: E501

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import Settings
from app.errors import ValidationError
from app.models import ModelCallRequest, ModelCallResponse, ModelOperation

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

PROMPT_TREND_ANALYSIS = """你是内容趋势分析师。基于一批小红书热帖数据（标题+互动数+标签+内容片段），分析该话题下的内容热点规律。
分析维度：
- themes：识别3~5个高频内容主题，每个给 count（相关帖子数）、topPost（代表帖标题）、engagement（高/中/低）、summary（一句话总结）
- viralPatterns：总结2~4个让内容高互动的共性规律，要落到可操作的创作建议上
- opportunityWindows：指出2~3个「需求强但供给少」的内容机会角度
只输出 JSON，不要解释。schema:
{"trendAnalysis":{"themes":[{"theme":"","count":0,"topPost":"","engagement":"高/中/低","summary":""}],"viralPatterns":[""],"opportunityWindows":[""]}}"""

PROMPT_TOPICS_B = """你是内容选题策略师。基于账号定位、热点趋势分析和评论区痛点，生成3~4个选题 + 2组标题变体。
重要约束：
① 每个选题必须同时满足：「话题热度高」AND「与账号定位匹配」
② topics[0] 必须对应 painPoints[0]（最高频痛点）
③ 每个选题带两个维度：whyFit（为什么适合这个账号）+ whyTrending（为什么现在是好时机）
④ titles 选 topics[0] 和 topics[1] 各给3条变体，利用热帖中验证过的标题模式
只输出 JSON，不要解释。schema:
{"topics":[{"title":"","angle":"","pain":"","whyFit":"","whyTrending":""}],"titles":[{"topic":"","variants":[]}]}"""

PROMPT_CONTENT_BRIEF = """你是创作者内容策划。用户已经从选题库中选择了一个选题。请把这个选题转成可执行的创作 brief，而不是直接写正文。
要求：
- 明确这个内容服务谁、为什么会点开、看完获得什么
- 判断它和账号定位是否一致
- 给出适合的内容形态和表达风险
- 输出要具体、可执行，避免泛泛而谈
- 不要润色成完整正文
只输出 JSON，不要解释。schema:
{"brief":{"topicTitle":"","refinedAngle":"","targetReader":"","readerPain":"","contentPromise":"","corePoint":"","formatRecommendation":"","openingHook":"","argumentPath":[],"materialNeeds":[],"titleDirections":[],"cta":"","risks":[],"revisionSuggestions":[]}}"""

PROMPT_SIMULATION_PERSONAS = """你是创作者内容策略中的受众研究员。基于账号定位和选题，推导 4 个产品内置的目标受众角色。
每个 persona 必须具体、有不同决策视角，不要把它们写成可配置 agent。
只输出 JSON，不要解释。schema:
{"personas":[{"id":"","name":"","profile":"","coreConcern":"","contentPreference":""}]}"""

PROMPT_SIMULATION_REACTION = """你正在模拟一个具体受众角色对选题的第一反应。
必须基于 persona 的视角，输出真实、简短、可用于判断内容风险和机会的反馈。
只输出 JSON，不要解释。schema:
{"reaction":{"personaId":"","stance":"喜欢/犹豫/反感","quote":"","concerns":[],"opportunities":[]}}"""

PROMPT_SIMULATION_DEBATE = """你正在模拟一个具体受众角色在看到其他人的第一反应后，给出第二轮回应。
必须接收其他人的反应，并说明自己的观点是否变化。
只输出 JSON，不要解释。schema:
{"debateResponse":{"personaId":"","response":"","changedMind":false,"newConcerns":[],"strongerSignals":[]}}"""

PROMPT_SIMULATION_SYNTHESIS = """你是内容策略师。基于完整受众模拟讨论，合成对该选题的判断。
输出应包含是否值得做、最大阻力、应强化的表达、应避开的表达。
只输出 JSON，不要解释。schema:
{"synthesis":{"verdict":"","mainResistance":"","strongestAngle":"","contentAdjustments":[],"riskWarnings":[]}}"""

PROMPT_AGENT_CHAT = """你是创作者 workspace 中的产品内 Agent。
你会收到：
- agent 定义：包括名称、用途、system prompt、关联 skill
- workspace context pack：账号资料、素材、分析、选题、草稿、受众模拟、Skills、Agents、Workflows 的全局视野
- conversation history：当前对话历史
- user message：用户最新消息

行为规则：
- 充分利用 workspace context pack 中的资产，但不要编造不存在的资产。
- 可以提出修改资产、创建选题、生成草稿等建议，但不能声称已经执行写入。
- 若用户表达修改意图，放入 proposedActions，status 必须是 requires_confirmation。
- proposedActions 可以包含 payload。只有你能明确字段时才给 payload；不要伪造资产 id。
- 常用类型：
  - workspace.update_profile payload: {"name":"","accountPositioning":""}
  - topic.create_or_update payload: {"title":"","angle":"","associatedPainPoint":"","whyItFits":""}
  - skill.propose_definition / agent.propose_definition / workflow.propose_definition payload: {"definition":{...}}
- 能力资产 proposal 必须给出可应用的完整 definition，不要只给空 payload。
- 如果是在修改当前选中的能力资产，可以在 payload 放入 targetAssetId；否则使用 definition 中的 skillId / agentId / workflowId 创建新资产，或命中同 stable id 时更新。
- skill definition 字段：skillId, displayName, category, purpose, triggerIntents, requiredInputs, optionalInputs, contextPolicy, outputSchema, artifactEffect, sideEffects, failureMode, composableWith, implementationRefs, version。
- agent definition 字段：agentId, displayName, purpose, systemPrompt, skillIds, defaultContextPolicy, version。skillIds 必须来自已有 capability catalog。
- workflow definition 字段：workflowId, displayName, purpose, entryAgentIds, agentPlan, artifactEffect, version，可选 callBinding。entryAgentIds、task.agentId、task.skillIds 必须来自已有 capability catalog。
- workflow callBinding 只能是 ""、"account"、"trend"、"video"。它表示把 workflow asset 注册到已有产品执行入口，不代表任意 workflow 图都能自动执行。
- 回复要直接、具体、中文优先。
- 不要输出 markdown 代码块。

只输出 JSON。schema:
{"reply":"","proposedActions":[{"type":"","status":"requires_confirmation","description":"","payload":{}}]}"""

PROMPT_VIDEO_CREATOR_PROFILE = """你是 AIGC 视频创作者运营分析师。基于创作者证据包、视频样本记录、链接备注、转写、画面观察和数据线索，给出创作者画像。
重点判断创作者主要驱动类型：
- script_driven：剧本/叙事/角色设定驱动，适合被激励计划放大
- commercial_driven：商单/带货/品牌合作驱动，平台激励计划通常很难改变行为
- tech_exploration_driven：技术探索/模型实验驱动，需要具体分类讨论
- mixed：多种驱动混合
- unclear：证据不足
要求：
- evidence 必须引用输入中的具体观察，不要编造视频内容
- 必须遵守 videoCreatorEvidencePack.evidenceLimitations；如果没有 hasVideoUnderstanding，不要声称看过镜头、剪辑、口型或完整视频
- 对推断性判断要标明“基于标题/正文/评论/封面推测”
- 不要把单个爆款等同于长期能力
- evidenceScope 直接复述输入证据包里的 evidenceScope
- evidenceConfidence 根据证据范围填写 高/中/低
- evidenceLimitations 必须包含输入证据包里的限制
- recommendedNextEvidence 说明还需要补什么证据才能提升判断可靠性
- 输出中文
只输出 JSON，不要解释。schema:
{"creatorProfile":{"creatorType":"","typeConfidence":"高/中/低","summary":"","audiencePositioning":"","contentPillars":[],"motivationSignals":[],"evidence":[],"uncertainties":[],"evidenceScope":{},"evidenceConfidence":"高/中/低","evidenceLimitations":[],"recommendedNextEvidence":[]}}"""

PROMPT_VIDEO_QUALITY_ANALYSIS = """你是 AIGC 视频质量评审。基于创作者证据包和已确认媒体理解结果，评估其内容质量、可持续生产能力和可被运营放大的程度。
评估维度：
- scriptAndNarrative：剧本、叙事、冲突、完播潜力
- visualExecution：画面完成度、镜头、剪辑、审美一致性
- aigcTechniqueUse：AIGC 技术使用是否服务内容，而不是只展示技术
- originality：原创表达与差异化
- consistency：账号连续性和系列化潜力
- audienceFit：目标人群清晰度
- productionRepeatability：稳定产能和复制能力
证据边界：
- 如果没有 video_understanding，只能评估内容方向、系列化、互动和间接质量信号
- 如果只有封面/截图理解，visualExecution 只能给保守判断
- 不要编造未提供的视频画面、音频、转写、剪辑节奏
- evidenceScope 直接复述输入证据包里的 evidenceScope
- evidenceConfidence 根据证据范围填写 高/中/低
- evidenceLimitations 必须包含输入证据包里的限制
- cannotAssess 列出因为缺少视频/图片理解而不能可靠判断的维度
- recommendedNextEvidence 说明还需要补什么证据才能提升判断可靠性
score 为 0-100 的整数。必须给出 strengths、weaknesses 和 evidence。
只输出 JSON，不要解释。schema:
{"videoQuality":{"overallScore":0,"level":"高/中/低","dimensionScores":[{"dimension":"","score":0,"reason":""}],"strengths":[],"weaknesses":[],"evidence":[],"evidenceScope":{},"evidenceConfidence":"高/中/低","evidenceLimitations":[],"cannotAssess":[],"recommendedNextEvidence":[]}}"""

PROMPT_INCENTIVE_FIT_ANALYSIS = """你是创作者激励计划策略负责人。基于创作者画像和视频质量诊断，判断该 AIGC 视频创作者是否适配平台激励计划。
判断逻辑：
- 剧本驱动型：通常更适合激励计划，因为激励能放大持续生产与系列化
- 商单驱动型：通常不适合，激励很难改变其主要收益函数
- 技术探索驱动型：需要分类讨论；如果能转化为稳定内容栏目则条件适配，否则只适合技术共创或专项活动
- 混合型：给出主导驱动和可运营抓手
输出必须给出 recommendation：
- strong_fit
- conditional_fit
- weak_fit
- not_fit
并给出 rationale、conditions、risks、operatorActions。
- evidenceScope、evidenceConfidence、evidenceLimitations 和 recommendedNextEvidence 必须继承前序诊断的证据边界；不要把证据不足包装成确定结论。
只输出 JSON，不要解释。schema:
{"incentiveFit":{"recommendation":"","fitScore":0,"rationale":"","conditions":[],"risks":[],"operatorActions":[],"programMatch":{"bestProgramType":"","why":"","avoid":""},"evidenceScope":{},"evidenceConfidence":"高/中/低","evidenceLimitations":[],"recommendedNextEvidence":[]}}}"""


MAX_TOKENS = {
    ModelOperation.PROFILE: 1800,
    ModelOperation.PAIN_POINTS: 1000,
    ModelOperation.TOPICS: 2000,
    ModelOperation.CONTENT_BRIEF: 1800,
    ModelOperation.STRUCTURE: 1500,
    ModelOperation.TREND_ANALYSIS: 2000,
    ModelOperation.TREND_TOPICS: 2000,
    ModelOperation.SIMULATION_PERSONAS: 1600,
    ModelOperation.SIMULATION_REACTION: 1200,
    ModelOperation.SIMULATION_DEBATE: 1200,
    ModelOperation.SIMULATION_SYNTHESIS: 1600,
    ModelOperation.AGENT_CHAT: 2000,
    ModelOperation.VIDEO_CREATOR_PROFILE: 1800,
    ModelOperation.VIDEO_QUALITY_ANALYSIS: 2200,
    ModelOperation.INCENTIVE_FIT_ANALYSIS: 1800,
}


class ModelCallService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def call(self, payload: ModelCallRequest) -> ModelCallResponse:
        return await self.call_operation(payload.operation, payload.context)

    async def call_operation(
        self, operation: ModelOperation, context: dict[str, Any]
    ) -> ModelCallResponse:
        provider = self.settings.model_provider.strip().lower()
        if provider == "anthropic":
            return await self._call_anthropic(operation, context)
        if provider in {"qwen", "dashscope"}:
            return await self._call_qwen(operation, context)
        raise ValidationError(
            "Unsupported MODEL_PROVIDER. Use 'anthropic', 'qwen', or 'dashscope'."
        )

    async def _call_anthropic(
        self, operation: ModelOperation, context: dict[str, Any]
    ) -> ModelCallResponse:
        if not self.settings.anthropic_api_key:
            raise ValidationError("ANTHROPIC_API_KEY is required for live generation")

        system, user = self._build_prompt(operation, context)
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                self._anthropic_messages_url(),
                headers={
                    "content-type": "application/json",
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.settings.anthropic_model,
                    "max_tokens": MAX_TOKENS[operation],
                    "temperature": 0.3,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        if response.status_code >= 400:
            raise ValidationError(f"Model call failed ({response.status_code})")

        body = response.json()
        text = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        )
        return ModelCallResponse(
            output=self._parse_model_output(operation, text),
            model_metadata={
                "provider": "anthropic",
                "model": body.get("model", self.settings.anthropic_model),
                "usage": body.get("usage", {}),
                "operation": operation.value,
            },
        )

    async def _call_qwen(
        self, operation: ModelOperation, context: dict[str, Any]
    ) -> ModelCallResponse:
        if not self.settings.qwen_api_key:
            raise ValidationError(
                "QWEN_API_KEY or DASHSCOPE_API_KEY is required for live generation"
            )

        system, user = self._build_prompt(operation, context)
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                headers={
                    "content-type": "application/json",
                    "authorization": f"Bearer {self.settings.qwen_api_key}",
                },
                json={
                    "model": self.settings.qwen_model,
                    "max_tokens": MAX_TOKENS[operation],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        if response.status_code >= 400:
            raise ValidationError(f"Model call failed ({response.status_code})")

        body = response.json()
        text = self._extract_openai_compatible_text(body)
        return ModelCallResponse(
            output=self._parse_model_output(operation, text),
            model_metadata={
                "provider": "qwen",
                "model": body.get("model", self.settings.qwen_model),
                "usage": body.get("usage", {}),
                "operation": operation.value,
            },
        )

    def _anthropic_messages_url(self) -> str:
        if self.settings.anthropic_messages_url.strip():
            return self.settings.anthropic_messages_url.strip()
        base_url = self.settings.anthropic_base_url.rstrip("/")
        if base_url.endswith("/apps/anthropic"):
            return f"{base_url}/v1/messages"
        return f"{base_url}/messages"

    def _build_prompt(
        self, operation: ModelOperation, context: dict[str, Any]
    ) -> tuple[str, str]:
        positioning = str(context.get("positioning", ""))
        if operation == ModelOperation.PROFILE:
            return (
                PROMPT_PROFILE,
                f"账号定位：\n{positioning}\n\n历史笔记：\n"
                f"{context.get('historicalPosts', '')}",
            )
        if operation == ModelOperation.PAIN_POINTS:
            source = context.get("sourceText", context.get("comments", ""))
            return (PROMPT_PAIN_POINTS, str(source))
        if operation == ModelOperation.TOPICS:
            return (
                PROMPT_TOPICS,
                "账号定位："
                f"{positioning}\n\n账号诊断：\n"
                f"{json.dumps(context.get('profile'), ensure_ascii=False)}\n\n"
                "评论痛点：\n"
                f"{json.dumps(context.get('painPoints'), ensure_ascii=False)}",
            )
        if operation == ModelOperation.STRUCTURE:
            return (
                PROMPT_STRUCTURE,
                f"账号定位：{positioning}\n\n热点背景：{context.get('background', '')}"
                f"\n\n选题：{context.get('topic', '')}",
            )
        if operation == ModelOperation.TREND_ANALYSIS:
            return (
                PROMPT_TREND_ANALYSIS,
                f"话题关键词：{context.get('trendKeyword', '（未指定）')}\n"
                f"账号定位：{positioning}\n\n热帖数据（按互动量排序）：\n"
                f"{context.get('postsText', '')}",
            )
        if operation == ModelOperation.TREND_TOPICS:
            return (
                PROMPT_TOPICS_B,
                "账号定位："
                f"{positioning}\n\n热点趋势分析：\n"
                f"{json.dumps(context.get('trendAnalysis'), ensure_ascii=False)}\n\n"
                "读者痛点：\n"
                f"{json.dumps(context.get('painPoints'), ensure_ascii=False)}",
            )
        if operation == ModelOperation.CONTENT_BRIEF:
            return (
                PROMPT_CONTENT_BRIEF,
                "账号定位："
                f"{positioning}\n\n选题：\n"
                f"{json.dumps(context.get('topic'), ensure_ascii=False)}\n\n"
                "分析背景：\n"
                f"{context.get('background', '')}",
            )
        if operation == ModelOperation.SIMULATION_PERSONAS:
            return (
                PROMPT_SIMULATION_PERSONAS,
                f"账号定位：{positioning}\n\n选题：\n"
                f"{json.dumps(context.get('topic'), ensure_ascii=False)}",
            )
        if operation == ModelOperation.SIMULATION_REACTION:
            return (
                PROMPT_SIMULATION_REACTION,
                "选题：\n"
                f"{json.dumps(context.get('topic'), ensure_ascii=False)}\n\n"
                "persona：\n"
                f"{json.dumps(context.get('persona'), ensure_ascii=False)}",
            )
        if operation == ModelOperation.SIMULATION_DEBATE:
            return (
                PROMPT_SIMULATION_DEBATE,
                "选题：\n"
                f"{json.dumps(context.get('topic'), ensure_ascii=False)}\n\n"
                "persona：\n"
                f"{json.dumps(context.get('persona'), ensure_ascii=False)}\n\n"
                "其他人的第一反应：\n"
                f"{json.dumps(context.get('otherReactions'), ensure_ascii=False)}",
            )
        if operation == ModelOperation.SIMULATION_SYNTHESIS:
            return (
                PROMPT_SIMULATION_SYNTHESIS,
                "选题：\n"
                f"{json.dumps(context.get('topic'), ensure_ascii=False)}\n\n"
                "personas：\n"
                f"{json.dumps(context.get('personas'), ensure_ascii=False)}\n\n"
                "第一反应：\n"
                f"{json.dumps(context.get('reactions'), ensure_ascii=False)}\n\n"
                "第二轮回应：\n"
                f"{json.dumps(context.get('debateResponses'), ensure_ascii=False)}",
            )
        if operation == ModelOperation.AGENT_CHAT:
            return (
                PROMPT_AGENT_CHAT,
                json.dumps(
                    {
                        "agent": context.get("agent"),
                        "workspaceContextPack": context.get("contextPack"),
                        "conversationHistory": context.get("messages"),
                        "userMessage": context.get("userMessage"),
                    },
                    ensure_ascii=False,
                ),
            )
        if operation == ModelOperation.VIDEO_CREATOR_PROFILE:
            return (
                PROMPT_VIDEO_CREATOR_PROFILE,
                f"激励计划/运营目标：\n{positioning}\n\n视频创作者证据包：\n"
                f"{json.dumps(context.get('videoCreatorEvidencePack', {}), ensure_ascii=False)}\n\n"
                "PM 可调 Rubric：\n"
                f"{json.dumps(context.get('pmRubric', {}), ensure_ascii=False)}\n\n"
                "兼容文本样本：\n"
                f"{context.get('videoCreatorSamples', '')}\n\n"
                "已确认的图片/视频媒体理解结果（compact snapshot）：\n"
                f"{json.dumps(context.get('mediaAssets', []), ensure_ascii=False)}",
            )
        if operation == ModelOperation.VIDEO_QUALITY_ANALYSIS:
            return (
                PROMPT_VIDEO_QUALITY_ANALYSIS,
                "激励计划/运营目标：\n"
                f"{positioning}\n\n创作者画像：\n"
                f"{json.dumps(context.get('creatorProfile'), ensure_ascii=False)}\n\n"
                "视频创作者证据包：\n"
                f"{json.dumps(context.get('videoCreatorEvidencePack', {}), ensure_ascii=False)}\n\n"
                "PM 可调 Rubric：\n"
                f"{json.dumps(context.get('pmRubric', {}), ensure_ascii=False)}\n\n"
                "兼容文本样本：\n"
                f"{context.get('videoCreatorSamples', '')}\n\n"
                "已确认的图片/视频媒体理解结果（compact snapshot）：\n"
                f"{json.dumps(context.get('mediaAssets', []), ensure_ascii=False)}",
            )
        if operation == ModelOperation.INCENTIVE_FIT_ANALYSIS:
            return (
                PROMPT_INCENTIVE_FIT_ANALYSIS,
                "激励计划/运营目标：\n"
                f"{positioning}\n\n创作者画像：\n"
                f"{json.dumps(context.get('creatorProfile'), ensure_ascii=False)}\n\n"
                "视频质量诊断：\n"
                f"{json.dumps(context.get('videoQuality'), ensure_ascii=False)}\n\n"
                "PM 可调 Rubric：\n"
                f"{json.dumps(context.get('pmRubric', {}), ensure_ascii=False)}",
            )
        raise ValidationError("Unsupported model operation")

    @classmethod
    def _parse_model_output(cls, operation: ModelOperation, text: str) -> dict[str, Any]:
        try:
            value = cls._parse_json(text)
        except ValidationError:
            if operation != ModelOperation.AGENT_CHAT:
                raise
            reply = text.strip()
            if not reply:
                raise
            return {"reply": reply, "proposedActions": []}
        return cls._validate_model_output(operation, value)

    @classmethod
    def _validate_model_output(
        cls, operation: ModelOperation, value: dict[str, Any]
    ) -> dict[str, Any]:
        requirements: dict[ModelOperation, dict[str, type | tuple[type, ...]]] = {
            ModelOperation.PROFILE: {"profile": dict},
            ModelOperation.PAIN_POINTS: {"painPoints": list},
            ModelOperation.TOPICS: {"topics": list},
            ModelOperation.CONTENT_BRIEF: {"brief": dict},
            ModelOperation.STRUCTURE: {"structure": dict},
            ModelOperation.TREND_ANALYSIS: {"trendAnalysis": dict},
            ModelOperation.TREND_TOPICS: {"topics": list},
            ModelOperation.SIMULATION_PERSONAS: {"personas": list},
            ModelOperation.SIMULATION_REACTION: {"reaction": dict},
            ModelOperation.SIMULATION_DEBATE: {"debateResponse": dict},
            ModelOperation.SIMULATION_SYNTHESIS: {"synthesis": dict},
            ModelOperation.AGENT_CHAT: {"reply": str, "proposedActions": list},
            ModelOperation.VIDEO_CREATOR_PROFILE: {"creatorProfile": dict},
            ModelOperation.VIDEO_QUALITY_ANALYSIS: {"videoQuality": dict},
            ModelOperation.INCENTIVE_FIT_ANALYSIS: {"incentiveFit": dict},
        }
        value = cls._normalize_output_aliases(operation, value)
        value = cls._unwrap_structured_output(operation, value, requirements)
        value = cls._normalize_output_aliases(operation, value)
        for key, expected_type in requirements.get(operation, {}).items():
            if key not in value:
                raise ValidationError(
                    f"Model response for {operation.value} missing {key}"
                )
            if not isinstance(value[key], expected_type):
                expected_name = cls._type_name(expected_type)
                raise ValidationError(
                    f"Model response field {key} must be {expected_name}"
                )
        if operation == ModelOperation.AGENT_CHAT and not value["reply"].strip():
            raise ValidationError("Model response field reply must not be blank")
        return value

    @staticmethod
    def _normalize_output_aliases(
        operation: ModelOperation, value: dict[str, Any]
    ) -> dict[str, Any]:
        aliases: dict[ModelOperation, dict[str, str]] = {
            ModelOperation.PAIN_POINTS: {"pain_points": "painPoints"},
            ModelOperation.TREND_ANALYSIS: {"trend_analysis": "trendAnalysis"},
            ModelOperation.AGENT_CHAT: {
                "proposed_actions": "proposedActions",
                "message": "reply",
                "answer": "reply",
            },
            ModelOperation.VIDEO_CREATOR_PROFILE: {
                "creator_profile": "creatorProfile"
            },
            ModelOperation.VIDEO_QUALITY_ANALYSIS: {"video_quality": "videoQuality"},
            ModelOperation.INCENTIVE_FIT_ANALYSIS: {"incentive_fit": "incentiveFit"},
            ModelOperation.CONTENT_BRIEF: {"contentBrief": "brief"},
        }
        operation_aliases = aliases.get(operation, {})
        normalized = dict(value)
        for source_key, target_key in operation_aliases.items():
            if target_key not in normalized and source_key in normalized:
                normalized[target_key] = normalized[source_key]
        return normalized

    @classmethod
    def _unwrap_structured_output(
        cls,
        operation: ModelOperation,
        value: dict[str, Any],
        requirements: dict[ModelOperation, dict[str, type | tuple[type, ...]]],
    ) -> dict[str, Any]:
        expected_keys = set(requirements.get(operation, {}))
        if not expected_keys or expected_keys.intersection(value):
            return value
        for wrapper_key in ("data", "result", "output"):
            nested = value.get(wrapper_key)
            if isinstance(nested, dict):
                nested = cls._normalize_output_aliases(operation, nested)
                if expected_keys.intersection(nested):
                    return nested
        return value

    @staticmethod
    def _type_name(expected_type: type | tuple[type, ...]) -> str:
        if isinstance(expected_type, tuple):
            return " or ".join(item.__name__ for item in expected_type)
        return expected_type.__name__

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        last_error: json.JSONDecodeError | None = None
        for candidate in ModelCallService._json_candidates(text):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError as error:
                last_error = error
                continue
            if not isinstance(value, dict):
                raise ValidationError("Model response JSON must be an object")
            return value
        raise ValidationError("Model response was not valid JSON") from last_error

    @staticmethod
    def _json_candidates(text: str) -> list[str]:
        stripped = text.strip()
        candidates = [stripped]
        fenced = re.search(
            r"```(?:json|JSON)?\s*(?P<body>.*?)\s*```",
            stripped,
            flags=re.DOTALL,
        )
        if fenced:
            candidates.append(fenced.group("body").strip())
        extracted = ModelCallService._extract_first_json_object(stripped)
        if extracted:
            candidates.append(extracted)
        deduped: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in deduped:
                deduped.append(candidate)
        return deduped

    @staticmethod
    def _extract_first_json_object(text: str) -> str | None:
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(text[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    @staticmethod
    def _extract_openai_compatible_text(body: dict[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValidationError("Model response missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ValidationError("Model response choice must be an object")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ValidationError("Model response missing message")
        content = message.get("content", "")
        if isinstance(content, str):
            if not content.strip():
                arguments = ModelCallService._extract_openai_compatible_arguments(message)
                if arguments:
                    return arguments
            return content
        if isinstance(content, list):
            text = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
            )
            if not text.strip():
                arguments = ModelCallService._extract_openai_compatible_arguments(message)
                if arguments:
                    return arguments
            return text
        raise ValidationError("Model response message content must be text")

    @staticmethod
    def _extract_openai_compatible_arguments(message: dict[str, Any]) -> str | None:
        function_call = message.get("function_call")
        if isinstance(function_call, dict):
            arguments = function_call.get("arguments")
            if isinstance(arguments, str) and arguments.strip():
                return arguments
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function")
                if not isinstance(function, dict):
                    continue
                arguments = function.get("arguments")
                if isinstance(arguments, str) and arguments.strip():
                    return arguments
        return None
