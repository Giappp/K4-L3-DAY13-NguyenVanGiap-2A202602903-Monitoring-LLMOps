from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)


def test_agent_records_prompt_version_with_v4_observation_api(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict] = []

    @contextmanager
    def record_attributes(**kwargs):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    span_update = client.span_updates[-1]
    assert span_update["metadata"] == {
        "doc_count": 1,
        "query_preview": "Explain traces",
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
        "prompt_fetch_error": "",
    }
    assert span_update["version"] == "3"
    assert propagated[0]["metadata"]["correlation_id"] == "req-12345678"
    assert propagated[-1]["prompt"] is client.prompt


class MockObservation:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class ObservingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []
        self.observations: list[MockObservation] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        obs = MockObservation(kwargs)
        self.observations.append(obs)
        yield obs


def test_agent_instruments_retrieval_and_generation_child_observations(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = ObservingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces to student@vinuni.edu.vn",
        correlation_id="req-99998888",
    )

    # Verify retrieval child observation
    retrieval_obs = next(obs for obs in client.observations if obs.kwargs["name"] == "retrieval")
    assert retrieval_obs.kwargs["as_type"] == "retriever"
    assert "student@" not in str(retrieval_obs.kwargs["input"])
    assert "[REDACTED_EMAIL]" in str(retrieval_obs.kwargs["input"])
    assert retrieval_obs.updates[-1]["metadata"]["doc_count"] >= 1

    # Verify generation child observation
    gen_obs = next(obs for obs in client.observations if obs.kwargs["name"] == "generation")
    assert gen_obs.kwargs["as_type"] == "generation"
    assert gen_obs.kwargs["model"] == "claude-sonnet-4-5"
    assert gen_obs.kwargs["prompt"] is client.prompt
    assert "usage_details" in gen_obs.updates[-1]
    assert "input" in gen_obs.updates[-1]["usage_details"]
    assert "output" in gen_obs.updates[-1]["usage_details"]
    assert "cost_details" in gen_obs.updates[-1]
    assert gen_obs.updates[-1]["cost_details"]["total"] > 0

