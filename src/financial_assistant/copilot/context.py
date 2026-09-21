"""Validate a small, data-only graph projection at the inference boundary."""
import json
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(max_length=300)]
Identifier = Annotated[str, Field(max_length=200)]

class StrictContext(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class CompactNode(StrictContext):
    id: Identifier
    kind: Text = ''
    label: Text = ''
    data: dict[Text, Text] = Field(default_factory=dict, max_length=30)

class Workspace(StrictContext):
    id: Identifier = ''
    type: Literal['investigation'] = 'investigation'
    title: Text = ''
    cutoff: Text = ''

class Investigation(StrictContext):
    id: Identifier = ''
    replay_id: Identifier = ''
    analysis_model: Text = ''

class Hypothesis(StrictContext):
    id: Identifier
    label: Text

class Summary(StrictContext):
    primary_claim: Text = ''
    counts: dict[Text, Annotated[int, Field(ge=0)]] = Field(default_factory=dict, max_length=50)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=8)
    supporting: int = Field(default=0, ge=0)
    weakening: int = Field(default=0, ge=0)
    missing_evidence: int = Field(default=0, ge=0)

class Relation(StrictContext):
    source: Identifier
    target: Identifier
    kind: Text

class View(StrictContext):
    filters: list[Text] = Field(default_factory=list, max_length=20)
    temporal_cutoff: Text = ''
    show_only_new: bool = False

class ViewContext(StrictContext):
    workspace: Workspace = Field(default_factory=Workspace)
    investigation: Investigation = Field(default_factory=Investigation)
    selection: CompactNode | None = None
    graph_summary: Summary = Field(default_factory=Summary)
    neighbourhood: list[Relation] = Field(default_factory=list, max_length=20)
    view: View = Field(default_factory=View)
    nodes: list[CompactNode] = Field(max_length=30)
    truncated: bool = False


def validate_context(raw):
    if not isinstance(raw, dict) or len(json.dumps(raw, ensure_ascii=False).encode()) > 24000:
        raise ValueError('ViewContext must be a compact object (maximum 24KB)')
    return ViewContext.model_validate(raw).model_dump()
