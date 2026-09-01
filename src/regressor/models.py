from enum import StrEnum


class Category(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    GENERAL = "general"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADVERSARIAL = "adversarial"
    
    
class FailureKind(StrEnum):
    """Why a case produced no usable answer.

    infra_*  -> we got no measurement. Affects completion rate.
    output_* -> we got a measurement and it was bad. Counts as a wrong answer.
    """
    INFRA_TIMEOUT = "infra_timeout"
    INFRA_RATE_LIMITED = "infra_rate_limited"
    INFRA_SERVER_ERROR = "infra_server_error"
    INFRA_TRANSPORT = "infra_transport"

    OUTPUT_SCHEMA_VIOLATION = "output_schema_violation"
    OUTPUT_REFUSAL = "output_refusal"
    OUTPUT_EMPTY = "output_empty"
    
    @property
    def is_infra(self)->bool:
        return self.value.startswith("infra_")
    