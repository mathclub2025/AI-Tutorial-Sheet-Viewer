"""Explicitly unavailable adapters: no fake answer or implicit DB."""

from app.core.errors import unavailable


class UnconfiguredQuestions:
    async def catalog(self, trace_id):
        raise unavailable("Question repository")

    async def search(self, request, trace_id):
        raise unavailable("Question repository")

    async def get(self, question_id, trace_id):
        raise unavailable("Question repository")

    async def similar(self, question_id, limit, trace_id):
        raise unavailable("Question repository")


class UnconfiguredAI:
    async def answer(self, request):
        raise unavailable("AI agent")

    async def explain(self, request):
        raise unavailable("AI agent")


class NoopCapture:
    async def record(self, event):
        return False


class UnconfiguredDocumentJobs:
    async def submit(self, request):
        raise unavailable("Document-processing agent")
