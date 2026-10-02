# LangChain and LangGraph pytest examples

Adapt field names and APIs to the installed versions; these target
`langchain-core` 1.x and `langgraph` 1.x. Generated checkpoint and interrupt
fields are not stable application contracts unless your wrapper makes them so.

## Canonical scripted tool-calling model

Why `GenericFakeChatModel` is not enough, and the rules this model follows, are
in [langchain-langgraph.md](langchain-langgraph.md#use-model-fakes-for-protocol-not-intelligence).
Keep one scripted model like this in the member's test support and reuse it
everywhere.

```python
# tests/app_testing/models.py
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.tool import tool_call
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, SkipValidation


class ScriptedToolChatModel(BaseChatModel):
    """Replays scripted replies in order and records what it was given.

    A scripted exception is raised at that step (a provider timeout, a refusal).
    Tool-call IDs in the script are ignored; each call mints fresh IDs.
    """

    # SkipValidation: pydantic cannot build a schema for arbitrary exceptions.
    script: SkipValidation[list[AIMessage | Exception]]
    seen: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tool_names: list[list[str]] = Field(default_factory=list)
    tool_choices: list[str | None] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-chat"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self.bound_tool_names.append(
            [convert_to_openai_tool(tool)["function"]["name"] for tool in tools]
        )
        self.tool_choices.append(tool_choice)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        call_number = len(self.seen)
        if call_number > len(self.script):
            raise AssertionError(f"unscripted call {call_number} to {self._llm_type}")
        template = self.script[call_number - 1]
        if isinstance(template, Exception):
            raise template
        reply = AIMessage(
            content=template.content,
            id=f"scripted-{call_number}",
            tool_calls=[
                tool_call(
                    name=call["name"],
                    args=call["args"],
                    id=f"call-{call_number}-{index}",
                )
                for index, call in enumerate(template.tool_calls)
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])
```

To script a provider failure, put the provider's own exception in the script
(for example `openai.APITimeoutError(request=...)`); the capability under test
must translate it into its port error. The OpenAI SDK builds its errors on its
HTTP client's `Request` and `Response` types; with openai 3.x that client is
`httpx2`, so constructing those errors in tests needs `httpx2` in the dev
dependency group even when production code never imports it.

It raises `AssertionError` rather than `UnexpectedCall` for the reason in
[core-principles.md](core-principles.md#doubles-must-be-correct) (LangChain's
async path). That path runs `_generate` in an executor, so the recorded lists
are still appended in call order.

## Agent tool round trip

One agent-stack test proves tool binding, argument decoding, execution, and
tool-call-ID correlation; the tool's business matrix stays in direct tool tests.

```python
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import tool_call

from app.genai.orders.tools import build_order_tools
from app_testing.models import ScriptedToolChatModel


@dataclass
class RecordingOrders:
    statuses: dict[str, str]
    lookups: list[str] = field(default_factory=list)

    def status_of(self, order_id: str) -> str:
        self.lookups.append(order_id)
        return self.statuses[order_id]


def test_agent_feeds_tool_result_back_to_model() -> None:
    orders = RecordingOrders(statuses={"order-7": "shipped"})
    model = ScriptedToolChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    tool_call(name="order_status", args={"order_id": "order-7"}, id=None)
                ],
            ),
            AIMessage(content="Order order-7 has shipped."),
        ]
    )
    agent = create_agent(model, tools=build_order_tools(orders))

    agent.invoke({"messages": [HumanMessage("Where is order-7?")]})

    assert orders.lookups == ["order-7"]
    tool_result = model.seen[1][-1]
    assert isinstance(tool_result, ToolMessage)
    assert tool_result.tool_call_id == "call-1-0"
    assert tool_result.content == "shipped"
```

## Pure router plus compiled graph

Test deterministic route policy directly, then keep a smaller graph test for
wiring. Build a fresh graph and checkpointer per test. `RefundGraph` is the
application's alias for its compiled graph type, for example
`CompiledStateGraph[RefundState, None, RefundState, RefundState]`.

```python
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from app.genai.refunds.graph import (
    RefundGraph,
    RefundState,
    build_refund_graph,
    route_after_risk,
)
from app_testing.models import ScriptedToolChatModel


@pytest.mark.parametrize(
    ("state", "expected_route"),
    [
        pytest.param(RefundState(risk_score=0.10), "auto_approve", id="low-risk"),
        pytest.param(RefundState(risk_score=0.91), "human_review", id="high-risk"),
    ],
)
def test_risk_route(state: RefundState, expected_route: str) -> None:
    assert route_after_risk(state) == expected_route


@pytest.fixture
def refund_graph() -> RefundGraph:
    model = ScriptedToolChatModel(script=[AIMessage(content='{"risk_score": 0.1}')])
    return build_refund_graph(model=model).compile(checkpointer=InMemorySaver())


def test_low_risk_refund_reaches_approval(refund_graph: RefundGraph) -> None:
    config: RunnableConfig = {"configurable": {"thread_id": "low-risk-refund-1"}}

    result = refund_graph.invoke(
        RefundState(refund_id="refund-4", amount_minor=500),
        config=config,
    )

    assert result["decision"] == "approved"
```

This does not prove the production model or saver. Test those in explicit
integration or live profiles.

## Interrupt and resume

The exact interrupt result representation is version-sensitive. The invariant
is stable: pause before the effect, resume on the same thread, and never
duplicate effects when the interrupted node restarts from its beginning.

```python
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.genai.approvals.graph import ApprovalGraph
from app_testing.payments import RecordingGateway


def test_approval_resume_charges_once(
    approval_graph: ApprovalGraph,
    recording_gateway: RecordingGateway,
) -> None:
    config: RunnableConfig = {"configurable": {"thread_id": "approval-22"}}

    paused = approval_graph.invoke(
        {"operation_id": "op-22", "amount_minor": 2500},
        config=config,
    )

    assert paused["__interrupt__"][0].value == {
        "operation_id": "op-22",
        "amount_minor": 2500,
    }
    assert recording_gateway.charges == []

    finished = approval_graph.invoke(
        Command(resume={"approved": True}),
        config=config,
    )

    assert finished["status"] == "captured"
    assert recording_gateway.charges == [("op-22", 2500)]
```

If code before the interrupt has a side effect, extend the recorder assertion
to prove resume does not repeat it. Add a real production-saver test for restart
and resume rather than inferring durability from `InMemorySaver`.
