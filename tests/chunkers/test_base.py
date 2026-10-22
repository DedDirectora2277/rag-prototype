from app.chunkers.base import Chunk, detect_ts_config, flatten


def test_flatten_puts_parents_before_children() -> None:
    tree = [
        Chunk('preamble', 'text'),
        Chunk(
            'section 5',
            'section',
            children=[
                Chunk('5.1', 'clause'),
                Chunk('5.2', 'clause', children=[Chunk('5.2 part', 'clause_part')]),
            ],
        ),
    ]

    records = flatten(tree, ts_config='english')

    assert [r.content for r in records] == ['preamble', 'section 5', '5.1', '5.2', '5.2 part']
    assert [r.parent_index for r in records] == [None, None, 1, 1, 3]
    assert [r.is_retrievable for r in records] == [True, False, True, False, True]
    assert {r.ts_config for r in records} == {'english'}
    assert all(r.embedding is None for r in records)


def test_flatten_ts_config_priority() -> None:
    records = flatten(
        [
            Chunk('def foo(): pass', 'function', ts_config='simple'),
            Chunk('Поставщик уплачивает неустойку', 'clause'),
            Chunk('The supplier shall pay a penalty', 'clause'),
        ]
    )

    assert [r.ts_config for r in records] == ['simple', 'russian', 'english']


def test_detect_ts_config() -> None:
    assert detect_ts_config('Договор поставки № 17') == 'russian'
    # Русский текст с английскими терминами остаётся русским.
    assert detect_ts_config('Настройка LiteLLM proxy через config.yaml') == 'russian'
    assert detect_ts_config('Supply agreement') == 'english'
    assert detect_ts_config('12 345') == 'english'
