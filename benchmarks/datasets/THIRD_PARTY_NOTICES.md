# Уведомления о сторонних данных

Вопросы, эталонные ответы и эталонные цитаты в `benchmarks/datasets/` частично взяты
из перечисленных ниже наборов данных и проектов. Сами документы корпуса в репозиторий не
входят: `python -m benchmarks.prepare_datasets` скачивает их из первоисточников
(источник и лицензия каждого файла — `benchmarks/corpus_manifest.json`).

## CUAD — Contract Understanding Atticus Dataset

- Файлы: `contracts.jsonl` (вопросы `cuad-*`).
- Авторы: The Atticus Project; Hendrycks D., Burns C., Chen A., Ball S.
  «CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review», NeurIPS 2021.
- Источник: https://www.atticusprojectai.org/cuad,
  https://huggingface.co/datasets/theatticusproject/cuad
- Лицензия: Creative Commons Attribution 4.0 International (CC BY 4.0),
  https://creativecommons.org/licenses/by/4.0/
- Изменения: служебные шаблоны вопросов CUAD («Highlight the parts (if any) of this
  contract related to…») заменены вопросами на естественном языке с названием договора и
  сторон; выбрано подмножество договоров и категорий. Эталонные фрагменты и ответы взяты
  из разметки CUAD без изменений.

## FinQA

- Файлы: `tables.jsonl` (вопросы `finqa-*`).
- Авторы: Chen Z., Chen W., Smiley C. и др. «FinQA: A Dataset of Numerical Reasoning over
  Financial Data», EMNLP 2021.
- Источник: https://github.com/czyssrs/FinQA, ревизия
  `0f16e2867befa6840783e58be38c9efb9229d742`.
- Изменения: выбрано по одному вопросу на компанию, в формулировку вопроса добавлено
  название компании, 8 вопросов с ошибочной исходной разметкой исключены; эталонные
  фрагменты — строки таблиц и предложения текста по разметке FinQA (`gold_inds`).
- Лицензия:

```text
MIT License

Copyright (c) 2021 Zhiyu Chen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## HTTPX

- Файлы: `code.jsonl` (вопросы `code-httpx-*`), цитаты из исходного кода и документации.
- Источник: https://github.com/encode/httpx, версия 0.28.1.
- Лицензия (BSD-3-Clause):

```text
Copyright © 2019, [Encode OSS Ltd](https://www.encode.io/).
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Click

- Файлы: `code.jsonl` (вопросы `code-click-*`), цитаты из исходного кода и документации.
- Источник: https://github.com/pallets/click, версия 8.1.8.
- Лицензия (BSD-3-Clause):

```text
Copyright 2014 Pallets

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1.  Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.

2.  Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

3.  Neither the name of the copyright holder nor the names of its
    contributors may be used to endorse or promote products derived from
    this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Русскоязычные документы

Цитаты в `contracts.jsonl`, `tables.jsonl` и `manual/` из ГК РФ (часть вторая) и
Федерального закона № 44-ФЗ (официальные документы, не являются объектами авторского
права, ст. 1259 ГК РФ), публичной оферты Яндекс Облака и раскрываемой отчётности
ПАО «Московская Биржа» и ПАО «МТС» приводятся в объёме, необходимом для эталонов,
с указанием источника в `benchmarks/corpus_manifest.json`.
