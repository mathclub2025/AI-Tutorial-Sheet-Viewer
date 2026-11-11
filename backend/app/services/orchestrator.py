"""Thin backend orchestration; retrieval and agent intelligence are owned by other teams."""

import logging

from app.core.errors import ServiceError
from app.domain.models import (
    AgentAnswer,
    AgentAnswerRequest,
    AgentExplainRequest,
    AskRequest,
    AskResponse,
    CatalogResponse,
    Citation,
    ExplainRequest,
    ExplainResponse,
    QueryEvent,
    Question,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SimilarResponse,
)
from app.domain.ports import AIProvider, QueryCapture, QuestionProvider

logger = logging.getLogger("mathclub.orchestrator")


class Orchestrator:
    def __init__(
        self,
        questions: QuestionProvider,
        ai: AIProvider,
        capture: QueryCapture,
        capture_required: bool = False,
    ):
        self.questions = questions
        self.ai = ai
        self.capture = capture
        self.capture_required = capture_required

    async def _capture(self, event: QueryEvent) -> bool:
        try:
            recorded = await self.capture.record(event)
            if self.capture_required and not recorded:
                raise ServiceError(
                    "CAPTURE_UNAVAILABLE", "Query capture is required but unavailable", 503
                )
            return recorded
        except ServiceError:
            if self.capture_required:
                raise
            logger.warning("query_capture_unavailable trace=%s", event.request_id)
            return False
        except Exception:
            if self.capture_required:
                raise ServiceError(
                    "CAPTURE_UNAVAILABLE", "Query capture is required but unavailable", 503
                )
            logger.warning("query_capture_failed trace=%s", event.request_id)
            return False

    @staticmethod
    def _hits(hits, filters=None, exclude_id=None):
        seen, output = set(), []
        for hit in hits:
            q = hit.question
            if filters:
                for field in ("subject", "module", "topic", "year", "source_type"):
                    expected = getattr(filters, field)
                    actual = getattr(q.source if field in {"year", "source_type"} else q, field)
                    if expected is not None and str(expected).casefold() != str(actual).casefold():
                        raise ServiceError(
                            "INVALID_UPSTREAM_RESPONSE",
                            "Search results violate requested filters",
                            502,
                        )
            if q.id != exclude_id and q.id not in seen:
                seen.add(q.id)
                output.append(hit)
        return output

    async def catalog(self, trace_id):
        result = await self.questions.catalog(trace_id)
        return CatalogResponse(**result.model_dump(), request_id=trace_id)

    @staticmethod
    def _citations(answer: AgentAnswer, available: list[Question]) -> list[Citation]:
        by_id = {question.id: question for question in available}
        used = list(dict.fromkeys(answer.used_question_ids))
        if any(question_id not in by_id for question_id in used):
            raise ServiceError(
                "INVALID_AI_CITATIONS", "AI referenced questions outside retrieved context", 502
            )
        return [
            Citation(question_id=question_id, source=by_id[question_id].source)
            for question_id in used
        ]

    async def search(self, request: SearchRequest, trace_id: str) -> SearchResponse:
        captured = await self._capture(
            QueryEvent(
                event_type="search",
                request_id=trace_id,
                query=request.query,
                filters=request.filters,
            )
        )
        hits = self._hits(await self.questions.search(request, trace_id), request.filters)[
            : request.limit
        ]
        return SearchResponse(items=hits, total=len(hits), request_id=trace_id, captured=captured)

    async def ask(self, request: AskRequest, trace_id: str) -> AskResponse:
        captured = await self._capture(
            QueryEvent(
                event_type="ask",
                request_id=trace_id,
                query=request.query,
                question_id=request.question_id,
                filters=request.filters,
            )
        )
        if request.question_id:
            q = await self.get_question(request.question_id, trace_id)
            matches = [SearchHit(question=q, relevance_score=1.0)]
            prompt = request.query or q.text
        else:
            assert request.query is not None
            search_request = SearchRequest(
                query=request.query, filters=request.filters, limit=request.limit
            )
            matches = self._hits(
                await self.questions.search(search_request, trace_id), request.filters
            )[: request.limit]
            prompt = request.query
        if not matches:
            return AskResponse(
                status="no_matches",
                answer=None,
                matched_questions=[],
                request_id=trace_id,
                captured=captured,
            )
        context = [h.question for h in matches]
        agent_response = await self.ai.answer(
            AgentAnswerRequest(
                query=prompt,
                context=context,
                explanation_level=request.explanation_level,
                request_id=trace_id,
            )
        )
        citations = self._citations(agent_response, context)
        return AskResponse(
            status="answered",
            answer=agent_response.answer,
            citations=citations,
            matched_questions=matches,
            request_id=trace_id,
            captured=captured,
        )

    async def get_question(self, question_id: str, trace_id: str) -> Question:
        question = await self.questions.get(question_id, trace_id)
        if question is None:
            raise ServiceError("QUESTION_NOT_FOUND", "Question was not found", 404)
        if question.id != question_id:
            raise ServiceError(
                "INVALID_UPSTREAM_RESPONSE", "Question identity does not match request", 502
            )
        return question

    async def similar(self, question_id: str, limit: int, trace_id: str) -> SimilarResponse:
        # A missing ID should be a 404 even if similarity search returns an empty list.
        await self.get_question(question_id, trace_id)
        matches = self._hits(
            await self.questions.similar(question_id, limit, trace_id), exclude_id=question_id
        )[:limit]
        return SimilarResponse(items=matches, request_id=trace_id)

    async def explain(
        self, question_id: str, request: ExplainRequest, trace_id: str
    ) -> ExplainResponse:
        captured = await self._capture(
            QueryEvent(
                event_type="explain",
                request_id=trace_id,
                question_id=question_id,
                query=request.instruction,
            )
        )
        question = await self.get_question(question_id, trace_id)
        agent_response = await self.ai.explain(
            AgentExplainRequest(
                question=question,
                instruction=request.instruction,
                explanation_level=request.explanation_level,
                request_id=trace_id,
            )
        )
        return ExplainResponse(
            answer=agent_response.answer,
            citations=self._citations(agent_response, [question]),
            request_id=trace_id,
            captured=captured,
        )
