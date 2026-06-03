"""Prompt builders for LLM spam classification requests"""


def build_spam_detection_prompt(message_text: str) -> str:
    return (
        "Is the following message spam or malicious? "
        'Answer only "yes" or "no". '
        f"Message: {message_text}"
    )
