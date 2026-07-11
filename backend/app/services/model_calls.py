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
- workspace context pack：账号资料、素材、分析、选题、草稿、受众模拟的全局视野
- conversation history：当前对话历史
- user message：用户最新消息

行为规则：
- 充分利用 workspace context pack 中的资产，但不要编造不存在的资产。
- 可以提出修改资产、创建选题、生成草稿等建议，但不能声称已经执行写入。
- 若用户表达修改意图，放入 proposedActions，status 必须是 requires_confirmation。
- 回复要直接、具体、中文优先。
- 不要输出 markdown 代码块。

只输出 JSON。schema:
{"reply":"","proposedActions":[{"type":"","status":"requires_confirmation","description":""}]}"""


MAX_TOKENS = {
    ModelOperation.PROFILE: 1800,
    ModelOperation.PAIN_POINTS: 1000,
    ModelOperation.TOPICS: 2000,
    ModelOperation.STRUCTURE: 1500,
    ModelOperation.TREND_ANALYSIS: 2000,
    ModelOperation.TREND_TOPICS: 2000,
    ModelOperation.SIMULATION_PERSONAS: 1600,
    ModelOperation.SIMULATION_REACTION: 1200,
    ModelOperation.SIMULATION_DEBATE: 1200,
    ModelOperation.SIMULATION_SYNTHESIS: 1600,
    ModelOperation.AGENT_CHAT: 2000,
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
                "https://api.anthropic.com/v1/messages",
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
            output=self._parse_json(text),
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
            output=self._parse_json(text),
            model_metadata={
                "provider": "qwen",
                "model": body.get("model", self.settings.qwen_model),
                "usage": body.get("usage", {}),
                "operation": operation.value,
            },
        )

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
        raise ValidationError("Unsupported model operation")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        stripped = text.strip()
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise ValidationError("Model response was not valid JSON") from error
        if not isinstance(value, dict):
            raise ValidationError("Model response JSON must be an object")
        return value

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
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
            )
        raise ValidationError("Model response message content must be text")
