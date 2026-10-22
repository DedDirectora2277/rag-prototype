"""Генерация ответа строго по найденным контекстам со ссылками [n]."""

from collections.abc import Sequence

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.retrieval.hybrid import RetrievedChunk

NO_ANSWER = 'Нет данных в предоставленных документах.'

SYSTEM_PROMPT = f"""Ты — ассистент корпоративной базы знаний. Отвечай на вопрос пользователя \
только на основе приведённых фрагментов документов.

Правила:
1. Используй только факты из фрагментов. Не добавляй знаний извне и не домысливай.
2. После каждого утверждения ставь ссылку на фрагмент в квадратных скобках: [1], [2][3].
3. Числа, даты, суммы, имена, идентификаторы кода и номера пунктов переноси дословно.
4. Если во фрагментах нет ответа, ответь ровно: «{NO_ANSWER}» (на языке вопроса).
5. Если ответ есть лишь частично, ответь на эту часть и прямо скажи, чего во фрагментах нет.
6. Отвечай на языке вопроса, кратко и по существу."""


def format_contexts(contexts: Sequence[RetrievedChunk]) -> str:
    """Нумерует контексты для промпта: `[n] источник` и текст.

    Args:
        contexts: Найденные контексты.

    Returns:
        Блок фрагментов для сообщения пользователя.
    """
    blocks = []
    for n, ctx in enumerate(contexts, start=1):
        header = f'[{n}] {ctx.title or ctx.source}'
        if ctx.title and ctx.title != ctx.source:
            header += f' ({ctx.source})'
        blocks.append(f'{header}\n{ctx.content}')
    return '\n\n---\n\n'.join(blocks)


def build_messages(
    question: str, contexts: Sequence[RetrievedChunk]
) -> list[ChatCompletionMessageParam]:
    """Собирает сообщения для chat completion.

    Args:
        question: Вопрос пользователя.
        contexts: Найденные контексты.

    Returns:
        Системное сообщение с правилами и пользовательское с фрагментами и вопросом.
    """
    return [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {
            'role': 'user',
            'content': f'Фрагменты документов:\n\n{format_contexts(contexts)}\n\n'
            f'Вопрос: {question}',
        },
    ]


async def generate_answer(
    client: AsyncOpenAI,
    model: str,
    question: str,
    contexts: Sequence[RetrievedChunk],
    max_tokens: int = 1024,
) -> str:
    """Генерирует ответ по контекстам.

    Без контекстов LLM не вызывается: ответ заведомо «нет данных».

    Args:
        client: Клиент OpenAI, смотрящий на LiteLLM.
        model: Алиас чат-модели в LiteLLM.
        question: Вопрос пользователя.
        contexts: Найденные контексты.
        max_tokens: Лимит длины ответа.

    Returns:
        Текст ответа.
    """
    if not contexts:
        return NO_ANSWER
    response = await client.chat.completions.create(
        model=model,
        messages=build_messages(question, contexts),
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or '').strip() or NO_ANSWER
