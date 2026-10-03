"""Strict, versioned model/client contract. Exported through /openapi.json."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

ID = str
Verb = Literal['observe', 'move', 'ask', 'use', 'combine', 'allocate', 'negotiate', 'reason']
Arc = Literal['mystery', 'comedy', 'craft', 'journey', 'negotiation', 'festival']

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Condition(Contract):
    kind: Literal['knowledge', 'owner', 'location', 'resource', 'relationship', 'quest', 'promise']
    key: ID
    value: str | int | bool
    actor: ID = 'player'
    comparison: Literal['eq', 'gte', 'lte'] = 'eq'

class Effect(Contract):
    op: Literal['learn', 'move', 'transfer', 'consume', 'craft', 'resource', 'relationship', 'promise', 'reward']
    target: ID
    value: str | int | bool
    actor: ID = 'player'

class TraitUse(Contract):
    character: ID
    aspect: Literal['strength', 'weakness']
    explanation: str = Field(min_length=3, max_length=180)

class Action(Contract):
    id: ID
    verb: Verb
    label: str = Field(min_length=1, max_length=100)
    target: ID
    prerequisites: list[Condition] = Field(default_factory=list, max_length=12)
    effects: list[Effect] = Field(default_factory=list, max_length=12)
    feedback: str = Field(min_length=1, max_length=240)
    alternatives: list[str] = Field(default_factory=list, max_length=8)
    inputs: list[ID] = Field(default_factory=list, max_length=6)
    trait_use: TraitUse | None = None
    hotspot: ID | None = None

class Character(Contract):
    id: ID
    name: str
    location: ID
    motivation: str
    strength: str
    weakness: str
    knowledge: list[ID] = Field(default_factory=list)

class Item(Contract):
    id: ID
    name: str
    owner: ID
    asset: ID
    recipe: list[ID] = Field(default_factory=list, max_length=6)

class Quest(Contract):
    id: ID
    title: str
    required: bool = True
    dependencies: list[ID] = Field(default_factory=list)
    conditions: list[Condition] = Field(min_length=1)

class WorldExpansion(Contract):
    items: list[Item] = Field(default_factory=list, max_length=4)
    clues: dict[ID,str] = Field(default_factory=dict, max_length=4)
    quests: list[Quest] = Field(default_factory=list, max_length=2)

class StoryBlueprint(Contract):
    schema_version: Literal[2] = 2
    title: str = Field(min_length=1, max_length=60)
    theme: str = Field(min_length=1, max_length=100)
    arc: Arc
    goal: str = Field(min_length=1, max_length=150)
    conflict: str
    characters: list[Character] = Field(min_length=2, max_length=9)
    items: list[Item] = Field(default_factory=list, max_length=64)
    clues: dict[ID, str] = Field(min_length=2, max_length=80)
    quests: list[Quest] = Field(min_length=1, max_length=24)
    resources: dict[ID, int] = Field(default_factory=lambda: {'time': 12, 'materials': 6})
    promises: dict[ID, bool] = Field(default_factory=dict)
    promise_descriptions: dict[ID, str] = Field(default_factory=dict)
    twists: list[str] = Field(default_factory=list)
    closure: str
    solution_tag: str

class Illustration(Contract):
    scene: ID
    characters: dict[ID, ID] = Field(default_factory=dict, max_length=4)
    props: list[ID] = Field(default_factory=list, max_length=6)
    key_art: ID | None = None

class Interaction(Contract):
    id: ID
    kind: Literal['observe', 'evidence', 'items', 'dialogue', 'allocation']
    instruction: str = Field(min_length=1, max_length=180)
    actions: list[Action] = Field(min_length=1, max_length=8)
    # Optional sorting and distribution operate locally; the action is committed on turn submission.
    order: list[ID] = Field(default_factory=list, max_length=8)
    order_action: ID | None = None

class BookPage(Contract):
    schema_version: Literal[2] = 2
    id: ID
    title: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=260)
    illustration: Illustration
    interactions: list[Interaction] = Field(default_factory=list, max_length=3)
    callbacks: list[ID] = Field(default_factory=list, max_length=5)
    choices: list[dict] = Field(default_factory=list, max_length=16)

class StoryOpening(Contract):
    blueprint: StoryBlueprint
    page: BookPage

class StoryEvent(Contract):
    schema_version: Literal[2] = 2
    id: ID
    turn: int
    cause: list[ID]
    action_id: ID
    verb: Verb = 'observe'
    description: str
    effects: list[Effect]
    reason: str = ''
    trait_use: TraitUse | None = None
    interaction_kind: Literal['observe','evidence','items','dialogue','allocation'] | None = None
    expansion: WorldExpansion | None = None

class WorldState(Contract):
    schema_version: Literal[2] = 2
    version: int
    location: ID
    characters: dict[ID, Character]
    items: dict[ID, Item]
    resources: dict[ID, int]
    relationships: dict[ID, int]
    knowledge: list[ID]
    quests: dict[ID, str]
    promises: dict[ID, bool]
    rewards: list[ID]
    provenance: dict[str, ID]

class Ending(Contract):
    title: str
    text: str = Field(min_length=1, max_length=500)
    evidence: list[ID] = Field(min_length=1,description='已确认StoryEvent的稳定ID，不是页码、action ID或中文说明')
    discoveries: list[ID] = Field(description='当前state.knowledge中的线索ID，不是线索的中文文本')
    helped: list[ID] = Field(description='参与故事的character ID，例如player或npc.xionger，不是新角色')
    solution: str

class TurnProposal(Contract):
    schema_version: Literal[2] = 2
    page: BookPage | None = None
    events: list[StoryEvent] = Field(default_factory=list, max_length=3)
    # Free text resolves to a full action, never a letter. Ambiguity produces choices with no state change.
    resolved_action: Action | None = None
    clarification: list[Action] = Field(default_factory=list, max_length=3)
    ending: Ending | None = None
    expansion: WorldExpansion | None = None

class StorySettings(Contract):
    theme: str = Field(min_length=1, max_length=100)
    character: str
    age: Literal['6-8', '9-12'] = '6-8'
    pages: Literal[8, 12, 16, 20] = 12
    parent_mode: bool = False
    arc: Arc | None = None
    assets: list[ID] = Field(min_length=1, max_length=300)

class CreateRequest(Contract):
    settings: StorySettings
    idempotency_key: str = Field(min_length=8, max_length=100)

class Operation(Contract):
    action_id: ID
    order: list[ID] = Field(default_factory=list, max_length=8)
    amount: int | None = Field(default=None, ge=0, le=20)
    items: list[ID] = Field(default_factory=list, max_length=6)

class SubmitRequest(Contract):
    version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    operations: list[Operation] = Field(default_factory=list, max_length=16)
    text: str = Field(default='', max_length=200)
    reason: str = Field(default='', max_length=200)
    clarification_job: str = Field(default='', max_length=32)
    clarification_action: ID = ''

class SessionRequest(Contract):
    account_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{16,80}$')
    account_secret: str = Field(min_length=32, max_length=128)
    guardian_code: str = Field(min_length=8, max_length=128)
    consent: Literal[True]

class Review(Contract):
    approved: bool = Field(description='存在必须修复的事实/因果/关键图文/严重重复问题才false；true时issues必须为空')
    issues: list[str] = Field(default_factory=list, max_length=12,description='阻断提交、必须修复的具体问题，不填写可接受的观察或小建议')
    advice: list[str] = Field(default_factory=list,max_length=8,description='不阻断提交的小建议，与issues明确分开')

class Concept(Contract):
    arc: Arc
    title: str
    conflict: str
    solution_tag: str
    cast: list[str] = Field(min_length=2, max_length=4)

class Concepts(Contract):
    candidates: list[Concept] = Field(min_length=3, max_length=3)

class ConfirmedPage(BookPage):
    state_snapshot: WorldState
    discussion: str = ''

class PendingAction(Contract):
    job_id: str
    request: SubmitRequest
    phase: str

class StoryRecord(Contract):
    schema_version: Literal[2] = 2
    id: str
    settings: StorySettings
    blueprint: StoryBlueprint
    initial_blueprint: StoryBlueprint
    state: WorldState
    events: list[StoryEvent]
    pages: list[ConfirmedPage]
    manifest: dict[str, dict]
    ending: Ending | None
    status: Literal['active','complete','continued']
    mock: bool
    concepts: list[Concept]
    selected_concept: Concept
    usage: list[dict]
    pending: PendingAction | None = None

class JobTicket(Contract):
    job_id: str

class JobStatus(Contract):
    id: str
    story: str | None
    phase: Literal['queued','planning','generating','reviewing','committing','complete','failed']
    result: dict | None
    error: str | None
    metrics: list[dict]

class SessionToken(Contract):
    access_token: str
    expires_at: float
    mock: bool

class BookSummary(Contract):
    id: str
    title: str
    status: Literal['active','complete','continued']
    pages: int
    mock: bool
