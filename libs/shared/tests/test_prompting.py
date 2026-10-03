import json

from classifier_service.prompting import OUTPUT_JSON_SCHEMA, build_messages
from shared.categories import Category
from shared.classification import ClassifierOutput


def test_messages_are_system_then_examples_then_email(prompt) -> None:
    messages = build_messages(prompt, "My invoice is wrong.")
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[0]["content"] == prompt.system_prompt
    assert messages[-1]["content"] == "<email>\nMy invoice is wrong.\n</email>"


def test_few_shot_answer_is_valid_classifier_output(prompt) -> None:
    answer = build_messages(prompt, "anything")[2]["content"]
    parsed = ClassifierOutput.model_validate_json(answer)
    assert parsed.category is Category.BILLING
    assert json.loads(answer)["summary"] == "Customer wants a duplicate charge refunded."


def test_schema_lists_exactly_the_four_categories() -> None:
    enum = OUTPUT_JSON_SCHEMA["properties"]["category"]["enum"]
    assert enum == [c.value for c in Category]
    assert OUTPUT_JSON_SCHEMA["additionalProperties"] is False
