# Согласие LLM-судьи с ручной разметкой

Выборка: `benchmarks/review/answers_review.xlsx` (CUAD не входит). Каппа Коэна: < 0.4 — слабое, 0.4–0.6 — умеренное, 0.6–0.8 — существенное, > 0.8 — почти полное согласие.

| Показатель | n | Доля совпадений | Каппа | Взвешенная каппа |
|---|---|---|---|---|
| Отказ | 30 | 1.00 | 1.00 | — |
| Правильность | 30 | 0.87 | 0.72 | 0.83 |
| Все утверждения подтверждены | 25 | 0.92 | 0.47 | — |

## Правильность: человек (строки) × судья (столбцы)

| | верно | частично | неверно |
|---|---|---|---|
| верно | 19 | 3 | 0 |
| частично | 0 | 1 | 1 |
| неверно | 0 | 0 | 6 |

## Расхождения по правильности

| № | Вопрос | Человек | Судья | Обоснование судьи |
|---|---|---|---|---|
| 1 | `finqa-awk_2012_page_117.pdf-1` | верно | частично | The answer correctly identifies the specific line items ($74,360 and $46,961) mentioned in Context [1] as being reflected as 'other long-term liabilities'. However, the question asks for the 'total li |
| 9 | `ru-podryad-riski` | верно | частично | The answer correctly identifies that the contractor bears the risk, which is supported by Context [1]. However, it omits the important exception mentioned in both the context and the reference: if the |
| 13 | `ru-yc-limit-otvetstvennosti` | верно | частично | The answer correctly states the limit for direct damages (total payments for the last reporting period), which is supported by Context [2]. However, it misses the key fact from the reference that Yand |
| 19 | `ru-cross-pretenzii-kachestvo` | частично | неверно | The answer is incomplete and cut off. It fails to mention the key distinction regarding who initiates/expenses the expertise (GK RF: by request of any party in case of dispute, contractor pays; 44-FZ: |

## Расхождения по опоре на контекст

| № | Вопрос | Человек | Судья (подтверждено/утверждений) | Обоснование судьи |
|---|---|---|---|---|
| 12 | `code-httpx-max-redirects` | да | нет (1/2) | The answer correctly identifies the exception class `TooManyRedirects` which is supported by context [6]. However, it claims that no exact redirect limit is specified, whereas the reference explicitly |
| 19 | `ru-cross-pretenzii-kachestvo` | да | нет (0/2) | The answer is incomplete and cut off. It fails to mention the key distinction regarding who initiates/expenses the expertise (GK RF: by request of any party in case of dispute, contractor pays; 44-FZ: |
