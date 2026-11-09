"""Work items: everything the Builder does is one of these, processed by the same loop in build.py.

  feature     a roadmap feature request
  dep_update  a homemade library published a new version; upgrade to it
  fix         a bug/security ticket (from Blue later, or added by hand)
"""
from dataclasses import asdict, dataclass, field

KINDS = ("feature", "dep_update", "fix")

HEADERS = {
    "feature": "Feature request:",
    "dep_update": "Dependency update:",
    "fix": "Bug ticket:",
}


@dataclass
class WorkItem:
    kind: str
    id: str
    title: str
    text: str
    tick: int
    feature: int | None = None  # for features: its number in the roadmap (checks up to it must pass)
    extra: dict = field(default_factory=dict)  # e.g. {"lib": "mdlite", "version": "1.1.0"}

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown work item kind {self.kind!r}")

    def request(self) -> str:
        """The request part of the prompt (the code, errors and reply format are added by build.py)."""
        body = self.text if self.kind != "fix" else f"{self.title}\n\n{self.text}"
        return f"{HEADERS[self.kind]}\n\n{body.strip()}\n"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WorkItem":
        return cls(**d)


def feature_item(stage, tick: int) -> WorkItem:
    return WorkItem("feature", f"feature-{stage.number}", stage.title, stage.text, tick, feature=stage.number)
