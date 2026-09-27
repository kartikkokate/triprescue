import app.llm_explainer as llm_explainer
from app.impact_engine import propagate_disruption
from app.recovery_engine import generate_recovery_plans


def _force_no_llm(monkeypatch):
    """Deterministically exercise the fallback path regardless of whether this machine
    happens to have GEMINI_API_KEY set - the fallback must work with no network/creds."""
    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", None)


def test_explain_impact_falls_back_for_a_delay(fresh_state, monkeypatch):
    _force_no_llm(monkeypatch)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 180)
    disruption = {"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"}

    result = llm_explainer.explain_impact(disruption, report, graph)

    assert result["source"] == "rule-based"
    assert "delayed by 180 minutes" in result["explanation"]
    assert "Airport -> Hotel Transfer" in result["explanation"]  # TR1, which broke


def test_explain_impact_falls_back_for_a_cancellation(fresh_state, monkeypatch):
    _force_no_llm(monkeypatch)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "TR1", "cancel", 0)
    disruption = {"node_id": "TR1", "kind": "cancel", "reason": "operator_cancellation"}

    result = llm_explainer.explain_impact(disruption, report, graph)

    assert result["source"] == "rule-based"
    assert "was cancelled" in result["explanation"]


def test_explain_impact_falls_back_for_weather_with_no_single_origin_node(fresh_state, monkeypatch):
    """Weather disruptions have no single node_id - this must not crash on None."""
    _force_no_llm(monkeypatch)
    graph = fresh_state.graph
    disruption = {
        "node_id": None,
        "kind": "weather",
        "date": "2026-10-11",
        "severity": "severe",
        "reason": "weather (severe) on 2026-10-11",
    }
    result = llm_explainer.explain_impact(disruption, {}, graph)

    assert result["source"] == "rule-based"
    assert "severe weather event on 2026-10-11" in result["explanation"]


def test_explain_impact_notes_when_nothing_actually_breaks(fresh_state, monkeypatch):
    _force_no_llm(monkeypatch)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 0)
    disruption = {"node_id": "FL1", "kind": "delay", "delay_minutes": 0, "reason": "unspecified"}

    result = llm_explainer.explain_impact(disruption, report, graph)
    assert "stays unaffected" in result["explanation"]


def test_explain_plans_falls_back_and_names_the_top_plan(fresh_state, monkeypatch):
    _force_no_llm(monkeypatch)
    graph = fresh_state.graph
    propagate_disruption(graph, "FL1", "delay", 180)
    plans = generate_recovery_plans(graph)

    result = llm_explainer.explain_plans(plans, {"reason": "unspecified"})

    assert result["source"] == "rule-based"
    assert plans[0].label in result["explanation"]


def test_explain_impact_uses_gemini_text_and_skips_thought_parts(fresh_state, monkeypatch):
    import httpx

    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", "test-key")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [
                {"text": "internal reasoning", "thought": True},
                {"text": "Your flight is late, so the transfer breaks."},
            ]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(llm_explainer.httpx, "post", fake_post)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 180)
    disruption = {"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"}

    result = llm_explainer.explain_impact(disruption, report, graph)

    assert result == {"explanation": "Your flight is late, so the transfer breaks.", "source": "llm", "model": "gemini"}
    assert "test-key" not in captured["url"]  # key travels in a header, never the URL
    assert captured["headers"]["x-goog-api-key"] == "test-key"


def test_explain_impact_falls_back_when_gemini_errors(fresh_state, monkeypatch):
    import httpx

    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        llm_explainer.httpx,
        "post",
        lambda url, **kw: httpx.Response(404, json={}, request=httpx.Request("POST", url)),
    )
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 180)
    disruption = {"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"}

    assert llm_explainer.explain_impact(disruption, report, graph)["source"] == "rule-based"


def test_explain_impact_retries_backup_model_when_primary_overloaded(fresh_state, monkeypatch):
    import httpx

    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", "test-key")
    called = []

    def fake_post(url, **kw):
        called.append(url)
        if llm_explainer.BACKUP_MODEL_ID in url:
            body = {"candidates": [{"content": {"parts": [{"text": "Backup model answer."}]}}]}
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))
        return httpx.Response(503, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_explainer.httpx, "post", fake_post)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 180)
    disruption = {"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"}

    result = llm_explainer.explain_impact(disruption, report, graph)

    assert result == {"explanation": "Backup model answer.", "source": "llm", "model": "gemini"}
    assert len(called) == 2


def test_explain_impact_retries_backup_model_when_primary_times_out(fresh_state, monkeypatch):
    import httpx

    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", "test-key")

    def fake_post(url, **kw):
        if llm_explainer.BACKUP_MODEL_ID in url:
            body = {"candidates": [{"content": {"parts": [{"text": "Backup after timeout."}]}}]}
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))
        raise httpx.ReadTimeout("slow", request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_explainer.httpx, "post", fake_post)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 180)
    disruption = {"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"}

    assert llm_explainer.explain_impact(disruption, report, graph)["explanation"] == "Backup after timeout."


def _delay_fixture(fresh_state):
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 180)
    disruption = {"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"}
    return disruption, report, graph


def test_nugen_aligned_model_is_preferred_over_gemini(fresh_state, monkeypatch):
    import httpx
    from app import nugen_client

    monkeypatch.setattr(nugen_client, "NUGEN_API_KEY", "nugen-key")
    monkeypatch.setattr(nugen_client, "NUGEN_MODEL_ID", "model_triprescue")
    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", "gemini-key")
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert "nugen.in" in url, "Gemini must not be called when the aligned model answers"
        seen["body"] = json
        seen["auth"] = headers["Authorization"]
        body = {"choices": [{"message": {"content": "<think>scratch</think>Your transfer breaks; the hotel holds."}}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(nugen_client.httpx, "post", fake_post)
    result = llm_explainer.explain_impact(*_delay_fixture(fresh_state))

    assert result == {"explanation": "Your transfer breaks; the hotel holds.", "source": "llm", "model": "nugen-aligned"}
    assert seen["body"]["model"] == "model_triprescue"
    assert seen["auth"] == "Bearer nugen-key"
    # the aligned model is served the exact format it was trained on
    assert seen["body"]["messages"][1]["content"].startswith("TASK: EXPLAIN_IMPACT")


def test_falls_through_to_gemini_when_nugen_fails(fresh_state, monkeypatch):
    import httpx
    from app import nugen_client

    monkeypatch.setattr(nugen_client, "NUGEN_API_KEY", "nugen-key")
    monkeypatch.setattr(nugen_client, "NUGEN_MODEL_ID", "model_triprescue")
    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", "gemini-key")

    def fake_post(url, **kw):
        if "nugen.in" in url:
            return httpx.Response(503, json={}, request=httpx.Request("POST", url))
        body = {"candidates": [{"content": {"parts": [{"text": "Gemini answer."}]}}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm_explainer.explain_impact(*_delay_fixture(fresh_state))["model"] == "gemini"


def test_explain_rights_fallback_cites_dgca_for_a_cancelled_flight(fresh_state, monkeypatch):
    _force_no_llm(monkeypatch)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "cancel", 0)
    disruption = {"node_id": "FL1", "kind": "cancel", "reason": "operator_cancellation"}

    result = llm_explainer.explain_rights(disruption, report, graph)

    assert result["model"] == "rule-based"
    assert "full refund or an alternate flight" in result["explanation"]
    assert "INR 7500" in result["explanation"]  # FL1 block time is 2h -> 7,500 band


def test_explain_rights_fallback_drops_compensation_for_weather(fresh_state, monkeypatch):
    _force_no_llm(monkeypatch)
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "cancel", 0)
    disruption = {"node_id": "FL1", "kind": "cancel", "reason": "weather"}

    result = llm_explainer.explain_rights(disruption, report, graph)
    assert "beyond the airline's control" in result["explanation"]
