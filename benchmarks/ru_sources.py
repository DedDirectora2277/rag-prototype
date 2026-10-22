"""Русскоязычная часть корпуса: НПА, договоры-оферты и финансовая отчётность.

Тексты законов не являются объектами авторского права (п. 6 ст. 1259 ГК РФ), но в git
их всё равно не кладём: в корпус они скачиваются этим модулем, в манифесте остаются
ссылки и хеши. Вопросы к этим документам — в `benchmarks/datasets/manual/*_ru.jsonl`.
"""

import html
import logging
import re
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger('benchmarks.prepare')

Download = Callable[[str, str], Path]
WriteDoc = Callable[[dict[str, dict[str, str]], str, bytes, str, str], None]

CONSULTANT = 'https://www.consultant.ru'

# Документ корпуса → (заголовок, документ на consultant.ru, статьи в порядке следования).
# Статьи выбираются по номеру из оглавления документа.
LAWS: dict[str, tuple[str, str, list[str]]] = {
    'contracts/ru/gk_rf_glava_34_arenda.txt': (
        'Гражданский кодекс Российской Федерации (часть вторая). Глава 34. Аренда. '
        '§ 1. Общие положения об аренде',
        'cons_doc_LAW_9027',
        [str(n) for n in range(606, 626)],
    ),
    'contracts/ru/gk_rf_glava_37_podryad.txt': (
        'Гражданский кодекс Российской Федерации (часть вторая). Глава 37. Подряд. '
        '§ 1. Общие положения о подряде',
        'cons_doc_LAW_9027',
        [str(n) for n in range(702, 730)],
    ),
    'contracts/ru/44_fz_kontrakt.txt': (
        'Федеральный закон от 05.04.2013 № 44-ФЗ «О контрактной системе в сфере закупок '
        'товаров, работ, услуг для обеспечения государственных и муниципальных нужд». '
        'Статьи о контракте, его исполнении, изменении и расторжении',
        'cons_doc_LAW_144624',
        ['34', '94', '95'],
    ),
}

# Договоры-оферты: документ корпуса → (заголовок, URL, начало и конец текста договора
# на странице). Без маркеров в документ попадают меню сайта и ссылки на прошлые версии.
# Редакция не фиксируется URL (у текущей версии нет датированного адреса), поэтому
# скачанная страница остаётся в кеше, а её хеш — в манифесте.
OFFERS: dict[str, tuple[str, str, str, str]] = {
    'contracts/ru/oferta_yandex_cloud.txt': (
        'Оферта на заключение договора на использование Сервисов Платформы «Яндекс.Облако»',
        'https://yandex.ru/legal/cloud_oferta/ru/',
        'Российская Федерация, Москва',
        'Предыдущая версия документа',
    ),
}

# Финансовая отчётность: документ корпуса → URL. Файлы берутся как есть (xlsx и PDF
# с сайтов эмитентов); у PDF таблицы без рамок, pdfplumber находит их не всегда.
FIN_REPORTS: dict[str, str] = {
    'tables/ru/moex_msfo_databook_2q2026.xlsx': (
        'https://www.moex.com/media/ifrs-databook-2q-2026-rus2.xlsx'
    ),
    'tables/ru/moex_msfo_2q2026.pdf': (
        'https://www.moex.com/media/msfo/summary-micex-rts-fs-2q2026-rus.pdf'
    ),
    'tables/ru/mts_fin_rezultaty_4q2025.xlsx': (
        'https://storage.ir.mts.ru/mts-ir/images/documents/Fin_rezultaty_4kv_2025.xlsx'
    ),
    'tables/ru/mts_press_reliz_4q2025.pdf': (
        'https://storage.ir.mts.ru/mts-ir/images/documents/MTS_4kv_i_2025_press_reliz.pdf'
    ),
}

_PARAGRAPH = re.compile(r'<p[^>]*>(.*?)</p>', re.S)
# Абзацы текста закона на consultant.ru начинаются с якоря редакции `dst…`; у вставок
# с комментариями и судебной практикой таких якорей нет.
_LAW_ANCHOR = re.compile(r'\s*<a id="dst\d+">')
_TAG = re.compile(r'<[^>]+>')
_BLOCK_TAG = re.compile(r'</?(p|div|li|h[1-6]|tr|br|ul|ol|table)\b[^>]*>', re.I)
_SCRIPT = re.compile(r'<(script|style|noscript)\b.*?</\1>', re.S | re.I)


def _inline_text(fragment: str) -> str:
    return re.sub(r'[ \t ]+', ' ', html.unescape(_TAG.sub('', fragment))).strip()


def law_article_text(page: str) -> str:
    """Извлекает текст статьи закона со страницы consultant.ru.

    Args:
        page: HTML страницы статьи.

    Returns:
        Заголовок статьи и её абзацы, по одному на строку.
    """
    lines = [_inline_text(p) for p in _PARAGRAPH.findall(page) if _LAW_ANCHOR.match(p)]
    # Заголовок страницы: «ГК РФ Статья 614. Арендная плата».
    lines = [re.sub(r'^(ГК РФ|44-ФЗ)\s+', '', line) for line in lines if line]
    return '\n'.join(lines)


def page_text(page: str) -> str:
    """Грубо переводит HTML-страницу в текст: блочные теги становятся переводами строк.

    Args:
        page: HTML страницы.

    Returns:
        Текст без пустых строк.
    """
    text = _BLOCK_TAG.sub('\n', _SCRIPT.sub('', page))
    lines = (_inline_text(line) for line in text.split('\n'))
    return '\n'.join(line for line in lines if line)


def _article_links(toc: str, doc_id: str) -> dict[str, str]:
    links = re.findall(rf'<a[^>]+href="(/document/{doc_id}/[0-9a-f]+/)"[^>]*>(.*?)</a>', toc)
    result: dict[str, str] = {}
    for href, title in links:
        number = re.match(r'Статья (\d+(?:\.\d+)?)\.', _inline_text(title))
        if number:
            result.setdefault(number[1], href)
    return result


def _cached_page(download: Download, url: str, name: str) -> str:
    path = download(url, name)
    return path.read_text(encoding='utf-8')


def build_ru_corpus(
    manifest: dict[str, dict[str, str]], download: Download, write_doc: WriteDoc
) -> None:
    """Скачивает русскоязычные документы и кладёт их в корпус.

    Args:
        manifest: Манифест корпуса, дополняется документами.
        download: Функция скачивания в кеш (`url`, имя файла) → путь.
        write_doc: Функция записи документа в корпус и манифест.
    """
    for rel_path, (title, doc_id, articles) in LAWS.items():
        toc_url = f'{CONSULTANT}/document/{doc_id}/'
        links = _article_links(_cached_page(download, toc_url, f'ru/{doc_id}.html'), doc_id)
        parts = [title]
        for number in articles:
            page = _cached_page(download, CONSULTANT + links[number], f'ru/{doc_id}_{number}.html')
            parts.append(law_article_text(page))
        write_doc(manifest, rel_path, '\n\n'.join(parts).encode(), toc_url, 'public-domain')

    for rel_path, (title, url, start, end) in OFFERS.items():
        name = 'ru/' + re.sub(r'\W+', '_', url.split('//', 1)[1]).strip('_') + '.html'
        text = page_text(_cached_page(download, url, name))
        begin = text.index(start)
        body = text[begin : text.index(end, begin)].strip()
        write_doc(manifest, rel_path, f'{title}\n{body}'.encode(), url, 'публичная оферта')

    for rel_path, url in FIN_REPORTS.items():
        data = download(url, 'ru/' + rel_path.rsplit('/', 1)[1]).read_bytes()
        write_doc(manifest, rel_path, data, url, 'раскрытие информации эмитента')
