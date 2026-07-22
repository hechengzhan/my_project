from typing import TypedDict, Optional

class AgentState(TypedDict):
    input: str
    history: Optional[str]
    session_id: Optional[str]
    intent: Optional[str]
    result: Optional[str]
    sources: Optional[list]
