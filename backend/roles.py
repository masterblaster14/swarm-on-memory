"""
The five swarm roles and their asymmetric access to Bourdon.

Access is enforced SERVER-SIDE by Bourdon's federation registry:
each role is a registered member with a trust tier and per-namespace
read grants. Verified: a quarantined member sees only granted namespaces
and is denied trusted-only tools. The Skeptic gets no token at all -- its
Bourdon client is None, so it is structurally amnesiac.

Namespaces (write targets / L5 manifests):
  swarm-architect            decisions        (public)
  swarm-architect-reasoning  reasoning        (public, SEPARATE namespace)
  swarm-implementer          code artifacts
  swarm-reviewer             review verdicts
  swarm-curator              corrections + contradiction resolutions
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Role:
    id: str                      # federation member slug + primary write namespace
    label: str
    tier: str                    # "trusted" | "quarantined" | "none"
    grants: tuple[str, ...]      # namespaces this role may READ (quarantined only)
    reads: str                   # human description of read scope (for UI)
    writes: tuple[str, ...]      # namespaces this role WRITES to
    color: str
    persona: str                 # system prompt fragment


ARCHITECT = Role(
    id="swarm-architect",
    label="Architect",
    tier="trusted",
    grants=(),  # trusted => reads everything
    reads="Full read + write",
    writes=("swarm-architect", "swarm-architect-reasoning"),
    color="#7c5cff",
    persona=(
        "You are the ARCHITECT. You turn a developer ticket into explicit, "
        "atomic engineering DECISIONS: data types, naming conventions, auth "
        "approach, error handling. Each decision is short, testable, and "
        "unambiguous. You separate the DECISION (what) from your REASONING "
        "(why) -- they go to different memory namespaces. You read prior "
        "corrections and NEVER re-propose something the team has rejected; "
        "when a correction applies, you cite it."
    ),
)

IMPLEMENTER = Role(
    id="swarm-implementer",
    label="Implementer",
    tier="quarantined",
    grants=("swarm-architect",),  # decisions ONLY -- blind to reasoning
    reads="Decisions only",
    writes=("swarm-implementer",),
    color="#2dd4bf",
    persona=(
        "You are the IMPLEMENTER. You write code that satisfies the "
        "Architect's DECISIONS exactly. You can see the decisions but NOT "
        "the reasoning behind them -- implement the letter of each decision. "
        "You do not invent conventions; if a decision is silent, you write "
        "the minimal reasonable code and flag the gap."
    ),
)

REVIEWER = Role(
    id="swarm-reviewer",
    label="Reviewer",
    tier="quarantined",
    grants=("swarm-architect", "swarm-curator"),  # decisions + corrections
    reads="Decisions + corrections",
    writes=("swarm-reviewer",),
    color="#f59e0b",
    persona=(
        "You are the REVIEWER. You judge the Implementer's code against the "
        "remembered DECISIONS and past CORRECTIONS -- not against any "
        "argument the Implementer makes. You cannot see the Implementer's "
        "reasoning. For each decision, state PASS or FAIL with the specific "
        "memory entity you checked against."
    ),
)

SKEPTIC = Role(
    id="swarm-skeptic",
    label="Skeptic",
    tier="none",              # NO token issued
    grants=(),
    reads="No memory access",
    writes=(),               # cannot write -- has no client
    color="#ef4444",
    persona=(
        "You are the SKEPTIC. You have NO access to shared memory and no "
        "history. Judge the ticket and the proposed approach purely on first "
        "principles. You are forbidden from deferring to prior decisions or "
        "consensus -- you have never seen them. Raise the risks and "
        "alternatives a memory-primed agent would overlook."
    ),
)

CURATOR = Role(
    id="swarm-curator",
    label="Curator",
    tier="trusted",
    grants=(),  # trusted => reads everything
    reads="Full read + write",
    writes=("swarm-curator",),
    color="#ec4899",
    persona=(
        "You are the CURATOR. You read every agent's concurrent writes, "
        "detect CONTRADICTIONS (two agents asserting incompatible things "
        "about the same subject), and resolve each under a stated, visible "
        "policy. Your resolution policy, in order: (1) an explicit human "
        "CORRECTION always wins; (2) a higher-access agent's DECISION beats "
        "a lower-access agent's assumption; (3) the more recent write wins "
        "ties. Log every resolution with the policy clause you applied."
    ),
)

ALL_ROLES = [ARCHITECT, IMPLEMENTER, REVIEWER, SKEPTIC, CURATOR]
ROLES_BY_ID = {r.id: r for r in ALL_ROLES}

# The curator namespace holds corrections; agents granted it read corrections.
CORRECTION_NAMESPACE = "swarm-curator"
DECISION_NAMESPACE = "swarm-architect"
REASONING_NAMESPACE = "swarm-architect-reasoning"
