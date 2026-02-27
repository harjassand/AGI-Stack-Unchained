from __future__ import annotations

from tools.mission_control.chat_router_v2 import decide_chat_route_v2


def test_whats_12_plus_3_routes_to_direct_answer() -> None:
    decision = decide_chat_route_v2("whats 12+3")
    assert decision.kind == "DIRECT_ANSWER"
    assert decision.answer_text == "15"


def test_what_is_12_plus_3_routes_to_direct_answer() -> None:
    decision = decide_chat_route_v2("what is 12 plus 3")
    assert decision.kind == "DIRECT_ANSWER"
    assert decision.answer_text == "15"


def test_division_routes_to_direct_answer() -> None:
    decision = decide_chat_route_v2("12 / 4")
    assert decision.kind == "DIRECT_ANSWER"
    assert decision.answer_text == "3"


def test_non_arithmetic_routes_to_mission() -> None:
    decision = decide_chat_route_v2("solve dark matter")
    assert decision.kind == "MISSION"
