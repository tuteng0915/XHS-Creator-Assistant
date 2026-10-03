from app.models import ModelCallResponse, ModelOperation
from app.services.model_calls import ModelCallService
from app.services.reader_selection import ReaderSelectionInput
from app.services.reader_selection_prompt import MAX_SELECTION_PROMPT_BYTES, selection_prompt


class RealReaderSelectionProvider:
    def __init__(self, model_calls: ModelCallService):
        self.model_calls = model_calls

    async def select(self, inputs: ReaderSelectionInput) -> ModelCallResponse:
        if not inputs.candidates:
            return ModelCallResponse(
                output={"proposedReaders": [], "unmatchedReason": "当前账号尚无可用的模拟读者"},
                model_metadata={"operation": "reader_selection", "modelCalled": False,
                                "reason": "empty_candidate_pool"},
            )
        system, user = selection_prompt(inputs)
        response = await self.model_calls.call_operation(
            ModelOperation.READER_SELECTION, inputs.model_dump(mode="json", by_alias=True),
        )
        return response.model_copy(update={"model_metadata": {
            **response.model_metadata, "modelCalled": True,
            "candidateCount": len(inputs.candidates), "desiredCount": inputs.desired_count,
            "inputBytes": len((system + user).encode("utf-8")),
            "inputByteLimit": MAX_SELECTION_PROMPT_BYTES,
        }})
