"""Готовит корпус и вопросы бенчмарка: `python -m benchmarks.prepare_datasets`.

Скачивает публичные датасеты (CUAD, FinQA) и репозитории с кодом в `benchmarks/.cache/`,
раскладывает документы по `benchmarks/corpus/<domain>/` и пишет вопросы в
`benchmarks/datasets/<domain>.jsonl`. Вопросы, написанные вручную (русский корпус и код),
лежат в `benchmarks/datasets/manual/*.jsonl` и вливаются в те же файлы. Каждый эталонный
фрагмент проверяется на наличие в своём документе после парсинга. Состав корпуса с хешами
записывается в `benchmarks/corpus_manifest.json`.

Отбор детерминированный: при повторном запуске корпус и вопросы совпадают побайтно.
"""

import argparse
import datetime as dt
import hashlib
import io
import json
import logging
import re
import sys
import tarfile
import time
import zipfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

import docx
import httpx

from app.ingest.parsers import parse_bytes
from benchmarks.dataset import (
    CORPUS_DIR,
    DATASETS_DIR,
    DOMAINS,
    ROOT,
    Domain,
    Sample,
    evidence_in,
    normalize,
    read_samples,
    write_samples,
)
from benchmarks.ru_sources import build_ru_corpus

logger = logging.getLogger('benchmarks.prepare')

CACHE_DIR = ROOT / '.cache'
MANUAL_DIR = DATASETS_DIR / 'manual'
MANIFEST_PATH = ROOT / 'corpus_manifest.json'

# --- CUAD: англоязычные договоры с SEC EDGAR, CC BY 4.0 ---------------------------------

CUAD_URL = (
    'https://huggingface.co/datasets/theatticusproject/cuad/resolve/'
    'a3c393f5d103fd0c516374e4fdff676c8176dcb1/CUAD_v1/CUAD_v1.json'
)
# Договоры с вопросами: заголовок CUAD → как договор называется в вопросе. В корпусе
# из многих договоров вопрос «какое право применимо?» без указания договора неоднозначен.
CUAD_CONTRACTS = {
    '2ThemartComInc_19990826_10-12G_EX-10.10_6700288_EX-10.10_Co-Branding Agreement_ Agency '
    'Agreement': 'the co-branding and advertising agreement between i-Escrow and 2TheMart.com',
    'ABILITYINC_06_15_2020-EX-4.25-SERVICES AGREEMENT': (
        'the services agreement between the Provider and Telcostar Pte. Ltd. (2019)'
    ),
    'ADAMSGOLFINC_03_21_2005-EX-10.17-ENDORSEMENT AGREEMENT': (
        'the endorsement agreement between Adams Golf and Tom Watson'
    ),
    'ADIANUTRITION,INC_04_01_2005-EX-10.D2-RESELLER AGREEMENT': (
        'the reseller agreement between PivX Corporation and Detto Technologies'
    ),
    'AMBASSADOREYEWEARGROUPINC_11_17_1997-EX-10.28-ENDORSEMENT AGREEMENT': (
        'the Kathy Ireland endorsement agreement with Diplomat Ambassador Eyewear Group'
    ),
    'AMERICANPHYSICIANSCAPITALINC_03_31_2003-EX-10.26-AGENCY AGREEMENT': (
        'the MICOA agency agreement with Stratton, Cheeseman & Walsh-Nevada'
    ),
    'AMERICASSHOPPINGMALLINC_12_10_1999-EX-10.2-SITE DEVELOPMENT AND HOSTING AGREEMENT': (
        'the site development and hosting agreement between Hanover Direct and '
        'The Deerskin Companies'
    ),
    'ANIXABIOSCIENCESINC_06_09_2020-EX-10.1-COLLABORATION AGREEMENT': (
        'the collaboration agreement between Anixa Biosciences and OntoChem'
    ),
    'ASHWORTHINC_01_29_1999-EX-10.(D)-PROMOTION AGREEMENT AND NANTZ COMMUNICATIONS, INC.': (
        'the promotion agreement between Ashworth, Jim Nantz and Nantz Communications'
    ),
    'ASIANDRAGONGROUPINC_08_11_2005-EX-10.5-Reseller Agreement': (
        'the reseller agreement between Galaxy Telecom and Galaxy Telnet'
    ),
    'ATMOSENERGYCORP_11_22_2002-EX-10.17-TRANSPORTATION SERVICE AGREEMENT': (
        'the transportation service agreement between Arkansas Western Pipeline and '
        'Associated Natural Gas'
    ),
    'AURASYSTEMSINC_06_16_2010-EX-10.25-STRATEGIC ALLIANCE AGREEMENT': (
        'the strategic alliance agreement between Aura Systems and Zanotti East'
    ),
    'AgapeAtpCorp_20191202_10-KA_EX-10.1_11911128_EX-10.1_Supply Agreement': (
        'the ODM supply agreement between Organic Preparations and Agape ATP'
    ),
    'AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License '
    'Agreement': 'the joint content license agreement between WPT Enterprises and Zynga',
    'AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.34_11788308_EX-10.34_Sponsorship '
    'Agreement': 'the event sponsorship agreement between Newegg and Allied Esports',
    'Apollo Endosurgery - Manufacturing and Supply Agreement': (
        'the manufacturing and supply agreement between Apollo Endosurgery and Establishment Labs'
    ),
    'ArtaraTherapeuticsInc_20200110_8-K_EX-10.5_11943350_EX-10.5_License Agreement': (
        'the sponsored research and license agreement between the University of Iowa and ArTara'
    ),
    'BELLRINGBRANDS,INC_02_07_2020-EX-10.18-MASTER SUPPLY AGREEMENT': (
        'the master supply agreement between Premier Nutrition and Fonterra'
    ),
    'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING AGREEMENT': (
        'the co-hosting agreement between Network Associates and Software.net'
    ),
    'BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT AGREEMENT (1)': (
        'the development agreement between Cargill and Bioamber'
    ),
}
# Договоры без вопросов — дистракторы того же жанра (первые подходящие по алфавиту).
CUAD_DISTRACTORS = 10
CUAD_MIN_CHARS, CUAD_MAX_CHARS = 15_000, 60_000
CUAD_QUESTIONS_PER_CONTRACT = 3
# Ответы-спаны длиннее этого — целые разделы, а не ответ на вопрос.
CUAD_MAX_ANSWER_CHARS = 1500
# Категории CUAD → вопрос на естественном языке; `{c}` — название договора.
CUAD_QUESTIONS = {
    'Governing Law': 'Which jurisdiction’s law governs {c}?',
    'Expiration Date': 'What is the term of {c} and when does it expire?',
    'Renewal Term': 'Does {c} renew automatically, and for how long?',
    'Notice Period To Terminate Renewal': (
        'How much advance notice is required to prevent the renewal of {c}?'
    ),
    'Termination For Convenience': (
        'Can a party terminate {c} for convenience, without cause? On what notice?'
    ),
    'Anti-Assignment': 'Can {c} be assigned without the consent of the other party?',
    'Cap On Liability': 'Is liability under {c} capped, and to what amount?',
    'Exclusivity': 'What exclusivity obligations does {c} establish?',
    'Non-Compete': 'What non-compete restrictions does {c} impose?',
    'Audit Rights': 'What audit or inspection rights are provided in {c}?',
    'Insurance': 'What insurance must be maintained under {c}?',
    'Minimum Commitment': 'Is there a minimum purchase or volume commitment in {c}?',
    'License Grant': 'What license is granted under {c}?',
    'Warranty Duration': 'How long does the warranty last under {c}?',
}

# --- FinQA: страницы 10-K компаний S&P 500, CC BY 4.0 ------------------------------------

FINQA_URL = (
    'https://raw.githubusercontent.com/czyssrs/FinQA/'
    '0f16e2867befa6840783e58be38c9efb9229d742/dataset/test.json'
)
FINQA_QUESTIONS = 50
# Дистракторы — другие страницы отчётов тех же компаний: системе приходится выбирать
# нужную страницу среди похожих таблиц одного эмитента.
FINQA_DISTRACTORS = 30
# Тикер → название компании для вопроса (на год отчёта).
FINQA_COMPANIES = {
    'AAL': 'American Airlines Group',
    'AAPL': 'Apple',
    'ABC': 'AmerisourceBergen',
    'ABMD': 'Abiomed',
    'ADBE': 'Adobe',
    'ADI': 'Analog Devices',
    'AES': 'The AES Corporation',
    'ALLE': 'Allegion',
    'ALXN': 'Alexion Pharmaceuticals',
    'AMAT': 'Applied Materials',
    'AMT': 'American Tower',
    'ANET': 'Arista Networks',
    'ANSS': 'Ansys',
    'AON': 'Aon',
    'AOS': 'A. O. Smith',
    'APD': 'Air Products and Chemicals',
    'AWK': 'American Water Works',
    'BDX': 'Becton, Dickinson and Company',
    'BKNG': 'The Priceline Group',
    'BKR': 'Baker Hughes',
    'BLK': 'BlackRock',
    'BLL': 'Ball Corporation',
    'C': 'Citigroup',
    'CB': 'ACE Limited',
    'CDNS': 'Cadence Design Systems',
    'CDW': 'CDW',
    'CE': 'Celanese',
    'CMCSA': 'Comcast',
    'CME': 'CME Group',
    'D': 'Dominion Resources',
    'DG': 'Dollar General',
    'DISCA': 'Discovery Communications',
    'DISH': 'DISH Network',
    'DRE': 'Duke Realty',
    'DVN': 'Devon Energy',
    'DXC': 'DXC Technology',
    'ECL': 'Ecolab',
    'EL': 'The Estée Lauder Companies',
    'EMR': 'Emerson Electric',
    'EOG': 'EOG Resources',
    'ETFC': 'E*TRADE Financial',
    'ETR': 'Entergy',
    'FBHS': 'Fortune Brands Home & Security',
    'FIS': 'Fidelity National Information Services',
    'GIS': 'General Mills',
    'GPN': 'Global Payments',
    'GRMN': 'Garmin',
    'GS': 'Goldman Sachs',
    'HIG': 'The Hartford',
    'HII': 'Huntington Ingalls Industries',
}

# --- Код: открытые Python-репозитории (BSD-3-Clause), вопросы — в manual/code.jsonl -----

CODE_REPOS = {
    # имя → (репозиторий GitHub, тег, каталоги, которые попадают в корпус)
    'httpx': ('encode/httpx', '0.28.1', ('httpx/', 'docs/')),
    'click': ('pallets/click', '8.1.8', ('src/click/', 'docs/')),
}
CODE_EXTENSIONS = frozenset({'.py', '.md', '.rst'})

# Пауза после каждого скачивания: статьи законов идут десятками запросов к одному сайту.
DOWNLOAD_DELAY_S = 1.0
# consultant.ru иногда рвёт TLS-соединение после нескольких десятков запросов подряд.
DOWNLOAD_ATTEMPTS = 4

Manifest = dict[str, dict[str, str]]


def download(url: str, name: str) -> Path:
    """Скачивает файл в кеш, если его там ещё нет.

    Args:
        url: Адрес (с зафиксированной ревизией).
        name: Имя файла в `benchmarks/.cache/`.

    Returns:
        Путь к файлу в кеше.
    """
    path = CACHE_DIR / name
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info('скачиваю %s', url)
    part = path.with_suffix(path.suffix + '.part')
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            with httpx.stream('GET', url, follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                with part.open('wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
            break
        except httpx.TransportError as exc:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise
            logger.warning('%s: %s, повтор через %s с', url, exc, 5 * attempt)
            time.sleep(5 * attempt)
    part.rename(path)
    time.sleep(DOWNLOAD_DELAY_S)
    return path


def write_doc(manifest: Manifest, rel_path: str, data: bytes, url: str, license_: str) -> None:
    """Кладёт документ в корпус и регистрирует его в манифесте.

    Args:
        manifest: Манифест корпуса (путь → источник, лицензия, sha256).
        rel_path: Путь относительно `benchmarks/corpus/`.
        data: Содержимое файла.
        url: Откуда взят документ.
        license_: Лицензия источника.
    """
    path = CORPUS_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    manifest[rel_path] = {
        'url': url,
        'license': license_,
        'sha256': hashlib.sha256(data).hexdigest(),
    }


def _file_stem(title: str) -> str:
    return re.sub(r'[^\w.-]+', '_', title).strip('_')[:100]


def _clean_spans(spans: list[str]) -> list[str]:
    # В CUAD один и тот же спан иногда размечен дважды.
    return list(dict.fromkeys(re.sub(r'\s+', ' ', s).strip() for s in spans))


def build_cuad(manifest: Manifest) -> list[Sample]:
    """Готовит договоры CUAD и вопросы по ним.

    На каждый договор берётся до `CUAD_QUESTIONS_PER_CONTRACT` категорий; категории
    выбираются по возрастанию частоты использования, чтобы вопросы не сводились
    к «Governing Law» у всех договоров.

    Args:
        manifest: Манифест корпуса, дополняется документами CUAD.

    Returns:
        Вопросы домена `contracts`.
    """
    data = json.loads(download(CUAD_URL, 'CUAD_v1.json').read_bytes())['data']
    by_title = {d['title']: d['paragraphs'][0] for d in data}
    distractors = [
        title
        for title in sorted(by_title)
        if title not in CUAD_CONTRACTS
        and CUAD_MIN_CHARS <= len(by_title[title]['context']) <= CUAD_MAX_CHARS
    ][:CUAD_DISTRACTORS]
    for title in [*CUAD_CONTRACTS, *distractors]:
        rel_path = f'contracts/cuad/{_file_stem(title)}.txt'
        text = by_title[title]['context']
        write_doc(manifest, rel_path, text.encode(), CUAD_URL, 'CC-BY-4.0')

    used: Counter[str] = Counter()
    samples = []
    for title, name in CUAD_CONTRACTS.items():
        answers: dict[str, list[str]] = {}
        for qa in by_title[title]['qas']:
            found = re.search(r'"(.+?)"', qa['question'])
            if qa['is_impossible'] or found is None:
                continue
            spans = _clean_spans([a['text'] for a in qa['answers']])
            if found[1] in CUAD_QUESTIONS and sum(map(len, spans)) <= CUAD_MAX_ANSWER_CHARS:
                answers[found[1]] = spans
        order = list(CUAD_QUESTIONS)
        chosen = sorted(answers, key=lambda c: (used[c], order.index(c)))
        for category in chosen[:CUAD_QUESTIONS_PER_CONTRACT]:
            used[category] += 1
            spans = answers[category]
            slug = re.sub(r'\W+', '-', category.lower())
            samples.append(
                Sample(
                    id=f'cuad-{_file_stem(title)[:40].lower()}-{slug}',
                    domain='contracts',
                    question=CUAD_QUESTIONS[category].format(c=name),
                    ground_truth=' '.join(spans),
                    reference_contexts=spans,
                    evidence=[[s] for s in spans],
                    source_docs=[f'contracts/cuad/{_file_stem(title)}.txt'],
                    metadata={'source': 'cuad', 'category': category, 'language': 'en'},
                )
            )
    return samples


def _finqa_docx(item: dict[str, Any], company: str) -> bytes:
    """Собирает страницу отчёта FinQA в DOCX: текст до таблицы, таблица, текст после."""
    ticker, year, page = item['filename'].removesuffix('.pdf').split('/')
    document = docx.Document()
    title = f'{company} ({ticker}) annual report {year}, {page.replace("_", " ")}'
    document.core_properties.title = title
    document.add_heading(title, level=1)
    for sentence in item['pre_text']:
        document.add_paragraph(sentence)
    rows = item['table_ori']
    table = document.add_table(rows=len(rows), cols=max(map(len, rows)))
    for row, cells in zip(table.rows, rows, strict=True):
        for cell, value in zip(row.cells, cells, strict=False):
            cell.text = value
    for sentence in item['post_text']:
        document.add_paragraph(sentence)
    # Фиксированные метаданные, иначе DOCX отличается при каждом запуске.
    epoch = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
    document.core_properties.created = document.core_properties.modified = epoch
    buffer = io.BytesIO()
    document.save(buffer)
    return _stable_zip(buffer.getvalue())


def _stable_zip(data: bytes) -> bytes:
    """Перепаковывает zip (DOCX) с фиксированными датами файлов внутри архива."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, 'w') as dst:
        for item in src.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=(2000, 1, 1, 0, 0, 0))
            dst.writestr(info, src.read(item), compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


def _finqa_evidence(item: dict[str, Any]) -> list[list[str]]:
    """Эталонные фрагменты FinQA: строка таблицы — непустые ячейки, текст — предложение.

    Индексы берутся из ключей `gold_inds` (`table_3`, `text_2`): поля `ann_*_rows`
    у части вопросов пустые.
    """
    sentences = [*item['pre_text'], *item['post_text']]
    groups = []
    for key in item['qa']['gold_inds']:
        kind, index = key.split('_')
        if kind == 'table':
            groups.append([c.strip() for c in item['table_ori'][int(index)] if c.strip()])
        else:
            groups.append([sentences[int(index)]])
    return [g for g in groups if g]


def build_finqa(manifest: Manifest) -> list[Sample]:
    """Готовит страницы FinQA (DOCX с таблицей) и вопросы по ним.

    Берётся по одному вопросу на компанию (первый по id), плюс страницы-дистракторы.

    Args:
        manifest: Манифест корпуса, дополняется документами FinQA.

    Returns:
        Вопросы домена `tables`.
    """
    items = sorted(json.loads(download(FINQA_URL, 'finqa_test.json').read_bytes()), key=_id)
    chosen: dict[str, dict[str, Any]] = {}
    for item in items:
        ticker = item['filename'].split('/')[0]
        if ticker not in chosen and item['qa']['answer'] and ticker in FINQA_COMPANIES:
            chosen[ticker] = item
        if len(chosen) == FINQA_QUESTIONS:
            break
    pages = {item['filename'] for item in chosen.values()}
    distractors: dict[str, dict[str, Any]] = {}
    for item in items:
        ticker = item['filename'].split('/')[0]
        if ticker in chosen and ticker not in distractors and item['filename'] not in pages:
            distractors[ticker] = item
    extra = [distractors[t] for t in sorted(distractors)[:FINQA_DISTRACTORS]]

    samples = []
    for item in [*chosen.values(), *extra]:
        ticker, year, _ = item['filename'].split('/')
        rel_path = f'tables/finqa/{_file_stem(item["filename"].removesuffix(".pdf"))}.docx'
        company = FINQA_COMPANIES[ticker]
        write_doc(manifest, rel_path, _finqa_docx(item, company), FINQA_URL, 'CC-BY-4.0')
        if item is not chosen[ticker]:
            continue
        qa = item['qa']
        samples.append(
            Sample(
                id=f'finqa-{_file_stem(item["id"]).lower()}',
                domain='tables',
                question=f'According to the {year} annual report of {company}, {qa["question"]}',
                ground_truth=qa['answer'],
                reference_contexts=list(qa['gold_inds'].values()),
                evidence=_finqa_evidence(item),
                source_docs=[rel_path],
                metadata={'source': 'finqa', 'program': qa['program'], 'language': 'en'},
            )
        )
    return samples


def _id(item: dict[str, Any]) -> str:
    return str(item['id'])


def _repo_members(archive: Path, prefixes: tuple[str, ...]) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            # Первый компонент пути — `<repo>-<tag>/`.
            path = PurePosixPath(*PurePosixPath(member.name).parts[1:])
            if (
                member.isfile()
                and path.suffix in CODE_EXTENSIONS
                and str(path).startswith(prefixes)
                and (f := tar.extractfile(member)) is not None
            ):
                yield str(path), f.read()


def build_code(manifest: Manifest) -> None:
    """Раскладывает исходники и документацию репозиториев из `CODE_REPOS` по корпусу.

    Args:
        manifest: Манифест корпуса, дополняется файлами репозиториев.
    """
    for name, (repo, tag, prefixes) in CODE_REPOS.items():
        url = f'https://codeload.github.com/{repo}/tar.gz/refs/tags/{tag}'
        archive = download(url, f'{name}-{tag}.tar.gz')
        for path, data in _repo_members(archive, prefixes):
            write_doc(manifest, f'code/{name}/{path}', data, url, 'BSD-3-Clause')


def load_manual() -> list[Sample]:
    """Читает вопросы, написанные вручную (`benchmarks/datasets/manual/*.jsonl`)."""
    return [s for path in sorted(MANUAL_DIR.glob('*.jsonl')) for s in read_samples(path)]


def _doc_text(rel_path: str) -> str:
    path = CORPUS_DIR / rel_path
    doc = parse_bytes(path.read_bytes(), path.name, source=rel_path)
    cells = (' | '.join(row) for t in doc.tables for row in [t.header, *t.rows])
    return normalize('\n'.join([doc.text, *cells]))


def validate(samples: list[Sample]) -> list[str]:
    """Проверяет, что вопросы ссылаются на существующие документы и фрагменты.

    Args:
        samples: Вопросы всех доменов.

    Returns:
        Описания ошибок; пустой список — всё в порядке.
    """
    errors = []
    ids = Counter(s.id for s in samples)
    errors += [f'{i}: повторяющийся id' for i, n in ids.items() if n > 1]
    texts: dict[str, str] = {}
    for sample in samples:
        missing = [d for d in sample.source_docs if not (CORPUS_DIR / d).is_file()]
        if missing or not sample.source_docs:
            errors.append(f'{sample.id}: нет документов {missing}')
            continue
        if not sample.evidence:
            errors.append(f'{sample.id}: нет эталонных фрагментов')
        for d in sample.source_docs:
            if d not in texts:
                texts[d] = _doc_text(d)
        text = '\n'.join(texts[d] for d in sample.source_docs)
        errors += [
            f'{sample.id}: фрагмент не найден в документе: {group}'
            for group in sample.evidence
            if not evidence_in(group, text)
        ]
    return errors


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.prepare_datasets')
    parser.add_argument(
        '--check-only', action='store_true', help='только проверить готовые датасеты'
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

    if args.check_only:
        samples = [s for d in DOMAINS for s in read_samples(DATASETS_DIR / f'{d}.jsonl')]
    else:
        manifest: Manifest = {}
        samples = [*build_cuad(manifest), *build_finqa(manifest)]
        build_code(manifest)
        build_ru_corpus(manifest, download, write_doc)
        samples += load_manual()
        by_domain: dict[Domain, list[Sample]] = {d: [] for d in DOMAINS}
        for sample in samples:
            by_domain[sample.domain].append(sample)
        for domain, items in by_domain.items():
            write_samples(DATASETS_DIR / f'{domain}.jsonl', sorted(items, key=lambda s: s.id))
        MANIFEST_PATH.write_text(
            json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=1) + '\n',
            encoding='utf-8',
        )
        docs = Counter(p.split('/')[0] for p in manifest)
        logger.info('корпус: %s документов %s', len(manifest), dict(docs))

    logger.info('вопросы: %s', dict(Counter(s.domain for s in samples)))
    errors = validate(samples)
    for error in errors:
        logger.error(error)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
