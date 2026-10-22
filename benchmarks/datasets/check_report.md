# Автоматическая проверка вопросов

Сгенерировано `python -m benchmarks.check_questions --llm`. Флаг — повод посмотреть вопрос вручную, а не вердикт об ошибке.

Проверено вопросов: 197; помечено: 65.

| Источник | Вопросов | Помечено |
|---|---|---|
| cuad | 60 | 22 |
| finqa | 42 | 17 |
| manual | 95 | 26 |

Стоимость LLM-вызовов в этом запуске: $0.011.

## Причины

- решение моделью: 45
- LLM-вердикт: 16
- числа не из фрагментов: 11
- ответ не следует из фрагментов: 7
- в документе есть противоречие: 6
- фрагментов не хватает: 5
- вопрос неоднозначен: 3
- эталон есть ещё в 1 док.: 1

## Помеченные вопросы

### `cuad-2themartcominc_19990826_10-12g_ex-10.10_-expiration-date`

- **Флаги:** решение моделью: partial
- **Вопрос:** What is the term of the co-branding and advertising agreement between i-Escrow and 2TheMart.com and when does it expire?
- **Эталон:** The term of this Agreement shall continue for one (1) year following the Launch Date, unless earlier terminated as provided herein.
- **Замечание модели:** —
- **Ответ модели по документу:** The agreement’s term is **one (1) year following the Launch Date**. It may automatically renew for another **one (1) year** unless either party gives notice at least **thirty (30) days** before expiration. The specific expiration date is **NOT IN DOCUMENT**.
- **Сравнение:** partial; The one-year term following the Launch Date is correct, but the candidate adds unsupported automatic-renewal and 30-day notice provisions and does not state that expiration is one year after the Launch Date.

### `cuad-adamsgolfinc_03_21_2005-ex-10.17-endorse-exclusivity`

- **Флаги:** LLM-вердикт: suspect; в документе есть противоречие; решение моделью: partial
- **Вопрос:** What exclusivity obligations does the endorsement agreement between Adams Golf and Tom Watson establish?
- **Эталон:** During the term of this Agreement, CONSULTANT shall exclusively play/use the MANDATORY PRODUCT. CONSULTANT hereby gives and grants to ADAMS GOLF the exclusive right and license to use CONSULTANT'S ENDORSEMENT in connection with the manufacture, sale, distribution, advertising and promotion of PRODUCT in the CONTRACT TERRITORY. During the term of this Agreement, unless otherwise authorized at the sole discretion of ADAMS GOLF in writing, CONSULTANT shall not: A.give the right to use or permit the use of CONSULTANT'S name, facsimile signature, nickname, voice or likeness to any other manufacturer or seller of PRODUCT; B.sponsor or endorse PRODUCT made or sold by any other manufacturer or seller; or C.serve as a CONSULTANT or advisor of any other manufacturer or seller of PRODUCT.
- **Замечание модели:** The reference accurately states the general exclusivity obligations, but the excerpt adds material exceptions: Watson may endorse and play a redacted product under specified conditions, need not wear Adams equipment in certain ads, may use non-Adams clubs in the bag without endorsing them, and may replace a terminating endorsement with another one under stated terms.
- **Ответ модели по документу:** The agreement requires Tom Watson to: - Exclusively endorse Adams Golf products and not permit his name, signature, nickname, voice, or likeness to be used by another product manufacturer or seller. - Not sponsor or endorse products made or sold by another manufacturer or seller. - Not serve as a consultant or adviser to another product manufacturer or seller. - Exclusively play/use the mandatory Adams Golf products during SPGA and PGA events, although he may use non-Adams clubs, including a putter, if he does not endorse them. - When endorsing noncompetitive products, use Adams Golf products 
- **Сравнение:** partial; The candidate captures the core exclusivity restrictions, but adds details not stated in the reference and potentially overstates the requirement by saying Watson must exclusively endorse Adams products. The reference specifically requires exclusive use of the mandatory product and grants Adams exclusive rights to use Watson’s endorsement, with listed prohibitions.

### `cuad-adamsgolfinc_03_21_2005-ex-10.17-endorse-minimum-commitment`

- **Флаги:** решение моделью: no
- **Вопрос:** Is there a minimum purchase or volume commitment in the endorsement agreement between Adams Golf and Tom Watson?
- **Эталон:** In each and every calendar year of this Agreement, CONSULTANT shall achieve a satisfactory record of play in a minimum of [* ****] professional golf association events on the SPGA and/or PGA tour (which shall include both the PGA and SPGA Tour Skins Games). If for any reason, CONSULTANT should achieve a satisfactory record of play in less than [*****] SPGA and/or PGA tour events in a calendar year, he shall repay ADAMS GOLF an amount per event for each event under [*****] achieved in the given calendar year as follows: The agreed upon repayment amount per event per calendar year: 1. Year 1. $[*****] 2. Year 2 $[*****] 3. Year 3 $[*****] 4. Year 4 $[*****] 5. Year 5 $[*****] "MANDATORY PRODUCTS" shall mean the following ADAMS GOLF PRODUCTS that CONSULTANT must exclusively play/use in all Champions/Senior Professional Golf Association (SPGA) and Professional Golf Association (PGA) events at all times: [***** ] Confidential Material redacted and filed separately with the Commission. 2 1.[*****] 2.Sufficient [*****] to maintain total minimum of [*****] ADAMS GOLF [*****] (includes [*****])[*****] at all times
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The reference specifies minimum annual tournament participation and mandatory Adams Golf product usage, while the candidate says the information is not in the document.

### `cuad-adianutrition_inc_04_01_2005-ex-10.d2-re-audit-rights`

- **Флаги:** решение моделью: partial
- **Вопрос:** What audit or inspection rights are provided in the reseller agreement between PivX Corporation and Detto Technologies?
- **Эталон:** In addition, Detto shall make its offices and equipment available in person, upon reasonable notice, and to the extent feasible, remotely, to PivX to inspect and test Detto's physical and technical set-up to ensure that Detto is complying with its obligations under this Section. PivX shall have the right, at reasonable times and on reasonable notice, to inspect and audit the books and records of Detto to verify the accuracy of any statements.
- **Замечание модели:** —
- **Ответ модели по документу:** PivX may inspect and test Detto’s physical and technical setup to verify compliance with Detto’s security obligations. Under Section 2.5, Detto must make its offices and equipment available: - in person, upon reasonable notice; and - remotely, to the extent feasible. The inspection concerns Detto’s servers, computer systems, offices, and equipment, particularly to ensure that Qwik-Fix Pro and Documentation are appropriately secured and that Courseware object code cannot be improperly accessed, copied, or downloaded.
- **Сравнение:** partial; The candidate accurately describes PivX’s inspection and testing rights and the in-person/remote access terms, but omits PivX’s separate right to inspect and audit Detto’s books and records at reasonable times and on reasonable notice to verify statement accuracy.

### `cuad-adianutrition_inc_04_01_2005-ex-10.d2-re-cap-on-liability`

- **Флаги:** решение моделью: partial
- **Вопрос:** What limitations of liability does the reseller agreement between PivX Corporation and Detto Technologies contain?
- **Эталон:** EXCEPT FOR PIVX'S OBLIGATIONS UNDER SECTION 4.2, IN NO EVENT SHALL PIVX'S OR ITS LICENSORS' LIABILITY TO DETTO OR ANY THIRD PARTY ARISING OUT OF THIS AGREEMENT EXCEED THE TOTAL AMOUNT ACTUALLY RECEIVED BY PIVX HEREUNDER DURING THE PREVIOUS SIX (6) MONTHS. In the event of termination in accordance with Section 5.1, PivX shall not be liable to Detto because of such termination for compensation, reimbursement or damages on account of the loss of prospective profits or anticipated sales or on account of expenditures, inventory, investments, leases or commitments in connection with the business or goodwill of Detto.
- **Замечание модели:** —
- **Ответ модели по документу:** The agreement contains these liability limitations: - Under Section 4.3, except for PivX’s indemnification obligations under Section 4.2, PivX’s and its licensors’ total liability to Detto or any third party is capped at “the total amount actually received by PivX hereunder during the previous six (6) months.” - No party or PivX’s licensors is liable for loss of data, costs of procuring substitute goods or services, or any indirect, incidental, special, or consequential damages, under any cause of action, even if advised of the possibility. - The limitation applies notwithstanding any failure 
- **Сравнение:** partial; The candidate correctly states the six-month liability cap and Section 4.2 exception, but omits the separate termination limitation barring compensation, reimbursement, or damages for lost prospective profits/anticipated sales and related expenditures, inventory, investments, leases, commitments, or goodwill. It also adds limitations not stated in the reference.

### `cuad-agapeatpcorp_20191202_10-ka_ex-10.1_1191-exclusivity`

- **Флаги:** решение моделью: partial
- **Вопрос:** What exclusivity obligations does the ODM supply agreement between Organic Preparations and Agape ATP establish?
- **Эталон:** The Manufacturer grants exclusive rights to the Customer for the term of ten (10) years from the date of the signing of this agreement and for an indefinite period upon the customer fulfilling the minimum annual purchase requirement as listed in Schedule B. of this agreement. The Manufacturer covenants not to sell any product listed in this agreement, or product name (as listed in schedule A of this agreement) to any other party without prior written consent of the Customer. The Manufacturer hereby appoints the Customer to be the sole and exclusive agent for the promotion, sales, marketing, distribution and administration of the products listed in schedule A of this agreement based on minimum annual product purchase requirements as listed in Schedule B of this agreement. The Manufacturer agrees to give the Customer exclusive rights to the marketing, promotion and sales of the new products should the Customer decide to take on the new products.
- **Замечание модели:** —
- **Ответ модели по документу:** The agreement establishes that: - Organic Preparations appoints Agape ATP as the **sole and exclusive agent** for the promotion, sales, marketing, distribution, and administration of the Schedule A products. - Organic Preparations grants Agape ATP **exclusive rights for ten (10) years from the signing date**, continuing for an **indefinite period** if Agape ATP fulfills the minimum annual purchase requirements in Schedule B. - Organic Preparations may not assign its rights or obligations without Agape ATP’s prior written consent, and Agape ATP likewise requires Organic Preparations’ prior writ
- **Сравнение:** partial; The candidate correctly states the exclusive agency appointment and ten-year/indefinite exclusivity tied to Schedule B purchases, but omits the manufacturer’s covenant not to sell the listed products or product names to other parties without the customer’s written consent and the customer’s exclusive rights to market, promote, and sell new products. It also adds mutual assignment-consent provisions not stated in the reference.

### `cuad-americanphysicianscapitalinc_03_31_2003--exclusivity`

- **Флаги:** решение моделью: no
- **Вопрос:** What exclusivity obligations does the MICOA agency agreement with Stratton, Cheeseman & Walsh-Nevada establish?
- **Эталон:** In order to allow SC&W to expand the distribution system in Nevada with select and controlled subagents, an exclusive agency agreement will be negotiated which will spell out the terms and conditions of the relationship.
- **Замечание модели:** —
- **Ответ модели по документу:** SC&W agrees not to serve in a strategic marketing capacity for another insurer in Nevada while providing such services for MICOA or for one year thereafter.
- **Сравнение:** no; The candidate describes a non-compete obligation for SC&W, but the reference only states that an exclusive agency agreement will be negotiated to govern SC&W’s expansion through select, controlled Nevada subagents; it does not specify the one-year post-service restriction.

### `cuad-americasshoppingmallinc_12_10_1999-ex-10-cap-on-liability`

- **Флаги:** LLM-вердикт: suspect; вопрос неоднозначен; решение моделью: no
- **Вопрос:** What limitations of liability does the site development and hosting agreement between Hanover Direct and The Deerskin Companies contain?
- **Эталон:** In the event the Company terminates this Agreement, the Company shall pay to HDI a termination payment, (the "Termination Payment") the amount of which shall be an amount equal to the aggregate Net Sales for the twelve (12) months preceding the Termination Date less $800,000, the balance of which shall be divided by two.
- **Замечание модели:** The reference answer is supported by the evidence, but the question asks about the agreement between Hanover Direct and The Deerskin Companies, while the document excerpt identifies the parties only as HDI and the Company and the agreement filename names America Shopping Mall, Inc.; the parties are therefore not unambiguously identifiable.
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The candidate does not state the termination payment limitation: aggregate Net Sales for the preceding 12 months minus $800,000, divided by two.

### `cuad-americasshoppingmallinc_12_10_1999-ex-10-non-compete`

- **Флаги:** решение моделью: partial
- **Вопрос:** What non-compete restrictions does the site development and hosting agreement between Hanover Direct and The Deerskin Companies impose?
- **Эталон:** Except as provided in Section 6.2, during the term of this Agreement, the Company shall not participate in any project similar to the Site on the Internet with respect to Deerskin Products or products substantially similar to Deerskin Products (including, without limitation, the products of Wilson's House of Leather, Excelled and companies similar to Wilson's House of Leather and Excelled) During the term of this Agreement and for a period of two years after the expiration date of this Agreement, HDI shall not participate in any project similar to the Site on the Internet from which products substantially similar to Deerskin Products (including, without limitation, the products of Wilson's House of Leather, Excelled and and companies similar to Wilson's House of Leather and Excelled) are offered for sale to consumers on the Internet.
- **Замечание модели:** —
- **Ответ модели по документу:** - **The Deerskin Companies:** During the Agreement’s term, they may not participate in any Internet project similar to the Site involving Deerskin Products or substantially similar products. HDI has the exclusive right to use the “Deerskin” brand for a self-contained consumer-facing website offering Deerskin Products. - **Exception:** The Company may establish an Internet site offering closeout merchandise that may be identified as Deerskin-branded products. - **Hanover Direct (HDI):** During the Agreement and for **two years after its expiration**, HDI may not participate in any similar Inter
- **Сравнение:** partial; The candidate correctly states the main non-compete restrictions and the two-year post-term restriction on HDI, but adds details about HDI’s exclusive right to use the Deerskin brand and a closeout-merchandise exception that are not in the reference, while not clearly identifying the reference’s Section 6.2 qualification.

### `cuad-anixabiosciencesinc_06_09_2020-ex-10.1-c-audit-rights`

- **Флаги:** LLM-вердикт: suspect; ответ не следует из фрагментов; фрагментов не хватает; в документе есть противоречие; решение моделью: partial
- **Вопрос:** What audit or inspection rights are provided in the collaboration agreement between Anixa Biosciences and OntoChem?
- **Эталон:** Each Party will provide the other Party with the right to inspect such records, and upon request will provide copies of all such records, to the extent reasonably required for the exercise or performance of such other Party's rights or obligations under this Agreement, provided that any information disclosed under this Section 2.7 will be subject to the terms and conditions of Section 5. These records will be available for inspection during regular business hours upon reasonable notice by Anixa, or its duly authorized representative, at Anixa's expense, for three (3) years following the end of the calendar year in which such expenses are invoiced.
- **Замечание модели:** The reference answer adds terms not supported by the evidence and contradicts the excerpt: the excerpt states each Party retains records for at least three years after expiration or termination, while the reference says inspection by Anixa at Anixa's expense for three years after the calendar year of invoicing. The excerpt does not specify regular business hours, reasonable notice, Anixa's expense, or an invoicing-based period.
- **Ответ модели по документу:** Each Party has the right to inspect the other Party’s records of activities under the Research Program and Inventions, and may request copies of those records as reasonably required to exercise or perform its rights or obligations. Disclosed information is subject to the confidentiality terms of Section 5. Records must be retained for at least three (3) years after expiration or termination, or longer if required by applicable law or regulation.
- **Сравнение:** partial; The candidate captures mutual inspection and copying rights, reasonable necessity, and Section 5 confidentiality, but incorrectly changes the retention period trigger and adds a retention requirement. The reference specifies inspection during business hours on reasonable notice by Anixa or its representative, at Anixa’s expense, for three years following the end of the calendar year in which expenses are invoiced.

### `cuad-apollo_endosurgery_-_manufacturing_and_s-warranty-duration`

- **Флаги:** решение моделью: partial
- **Вопрос:** What warranty period or deadline for reporting defects applies under the manufacturing and supply agreement between Apollo Endosurgery and Establishment Labs?
- **Эталон:** APOLLO has the right to reject, via written notification to ESTABLISHMENT within this thirty (30) day period, any or all of a shipment of Product that fails to satisfy any warranty in this Agreement and may reject all of a given Lot of Product if a statistical sample does not meet the Specifications.
- **Замечание модели:** —
- **Ответ модели по документу:** APOLLO may inspect shipments and report defects in writing within thirty (30) business days of receiving each shipment.
- **Сравнение:** partial; The candidate captures the 30-day written reporting period but incorrectly states business days and omits that the period concerns rejecting products failing warranties, including possible rejection of an entire lot based on statistical sampling.

### `cuad-artaratherapeuticsinc_20200110_8-k_ex-10-audit-rights`

- **Флаги:** решение моделью: no
- **Вопрос:** What audit or inspection rights are provided in the sponsored research and license agreement between the University of Iowa and ArTara?
- **Эталон:** University will provide ArTara and CRO the opportunity to examine the originals of medical records and supporting records for the Program Data at the University during normal business hours and at mutually agreeable times.
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The candidate omits the audit/inspection right allowing ArTara and its CRO to examine original medical and supporting records for Program Data at the University during normal business hours at mutually agreeable times.

### `cuad-artaratherapeuticsinc_20200110_8-k_ex-10-cap-on-liability`

- **Флаги:** решение моделью: partial
- **Вопрос:** What limitations of liability does the sponsored research and license agreement between the University of Iowa and ArTara contain?
- **Эталон:** IN NO EVENT SHALL EITHER PARTY BE LIABLE TO THE OTHER PARTY UNDER THIS AGREEMENT IN A DIRECT ACTION BETWEEN THE PARTIES FOR SPECIAL, INDIRECT, INCIDENTAL OR CONSEQUENTIAL DAMAGES (INCLUDING, WITHOUT LIMITATION, LOSS OF PROFITS) SUFFERED BY THE OTHER PARTY.
- **Замечание модели:** —
- **Ответ модели по документу:** The agreement contains these liability limitations: - **No consequential damages:** Neither party is liable to the other in a direct action for “special, indirect, incidental or consequential damages,” including loss of profits (Section 6.4). - **Limited indemnification by ArTara:** ArTara’s indemnification covers liability, loss, expenses, attorneys’ fees, and injury or damage claims arising from use of the Program Data, but only “in proportion to and to the extent” caused by the negligence or acts or omissions of ArTara, its personnel, subcontractors, CRO, or Affiliates (Section 6.3). - **In
- **Сравнение:** partial; The candidate correctly states the mutual exclusion of special, indirect, incidental, and consequential damages, including lost profits. However, it adds indemnification and insurance provisions that are not part of the reference’s stated limitation of liability.

### `cuad-asiandragongroupinc_08_11_2005-ex-10.5-r-anti-assignment`

- **Флаги:** LLM-вердикт: suspect; в документе есть противоречие
- **Вопрос:** Can the reseller agreement between Galaxy Telecom and Galaxy Telnet be assigned without the consent of the other party?
- **Эталон:** Neither party may assign this Agreement without the prior written consent of the other.
- **Замечание модели:** The general rule is supported, but the excerpt adds exceptions: Galaxy may assign the entire agreement to an affiliate and assign accounts receivable to a financing institution without the other party’s consent.
- **Ответ модели по документу:** No. Under section 13.5, neither party may assign the Agreement without the other party’s prior written consent. However, Galaxy may assign the entire Agreement to an affiliate or assign accounts receivable to a financing institution without that consent.
- **Сравнение:** yes; 

### `cuad-atmosenergycorp_11_22_2002-ex-10.17-tran-expiration-date`

- **Флаги:** LLM-вердикт: suspect
- **Вопрос:** What is the term of the transportation service agreement between Arkansas Western Pipeline and Associated Natural Gas and when does it expire?
- **Эталон:** Subject to the General Terms and Conditions of Transporter's FERC Gas Tariff and Rate Schedule FTS/ITS, this Agreement shall be effective as of the date of physical completion of and initial deliveries on Transporter's pipeline and shall continue for a primary term of ten years.
- **Замечание модели:** The term is supported, but the reference answer does not state when the agreement expires. The document says it continues for ten years from physical completion and initial deliveries, then continues month-to-month until terminated with the applicable notice; no physical-completion or initial-delivery date is provided.
- **Ответ модели по документу:** The agreement has a primary term of ten years, beginning on the date of physical completion and initial deliveries on Transporter’s pipeline. It then continues month to month until terminated with written notice—60 days for interruptible service or 180 days for firm service. The expiration date is not specified in the document.
- **Сравнение:** yes; 

### `cuad-atmosenergycorp_11_22_2002-ex-10.17-tran-minimum-commitment`

- **Флаги:** решение моделью: no
- **Вопрос:** Is there a minimum purchase or volume commitment in the transportation service agreement between Arkansas Western Pipeline and Associated Natural Gas?
- **Эталон:** Quantity of capacity to be released: Max 13,370 Dfli/Day, Min 13,370 DthDay. Minimum transportation rate acceptable to Releasing Shipper (if none, write "none"; includes commodity component): Tariff Rate (ii) Bid Requirements: (a) _X_ Reservation, __Volumetric or ___ Volumetric with ___ volume commitment (b) __ Dollar/Cents or __ Percentage
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The reference specifies a minimum and maximum released capacity of 13,370 Dth/day and a tariff-rate minimum, with a reservation bid requirement; it does not say the information is absent.

### `cuad-aurasystemsinc_06_16_2010-ex-10.25-strat-cap-on-liability`

- **Флаги:** LLM-вердикт: suspect; ответ не следует из фрагментов; фрагментов не хватает; решение моделью: partial
- **Вопрос:** What limitations of liability does the strategic alliance agreement between Aura Systems and Zanotti East contain?
- **Эталон:** NEITHER PARTY SHALL NOT BE LIABLE TO THE OTHER FOR ANY DAMAGES, LOSSES OR EXPENSES RESULTING FROM ANY TERMINATION OR EXPIRATION OF THIS AGREEMENT ARISING FROM ANY CLAIMS ASSERTED WHICH ARE BASED UPON LOSS OF GOODWILL, PROSPECTIVE PROFITS OR ANTICIPATED ORDERS, OR ON ACCOUNT OF ANY EXPENDITURES, INVESTMENTS, LEASES OR COMMITMENTS MADE BY SUCH PARTY; IN NO EVENT SHALL EITHER PARTY BE LIABLE TO THE OTHER PARTY FOR ANY SPECIAL, CONSEQUENTIAL OR INDIRECT DAMAGES, HOWEVER CAUSED.
- **Замечание модели:** The excerpt directly supports the termination/expiration limitation, but does not contain the separate exclusion of special, consequential, or indirect damages. Thus the full reference answer is not established by the provided evidence.
- **Ответ модели по документу:** The agreement contains this limitation of liability upon termination or expiration: - “NEITHER PARTY SHALL NOT BE LIABLE TO THE OTHER FOR ANY DAMAGES, LOSSES OR EXPENSES” resulting from termination or expiration based on claims for: - loss of goodwill; - prospective profits; - anticipated orders; or - expenditures, investments, leases, or commitments made by that party. It also provides that neither party is discharged from antecedent obligations or liabilities unless agreed in writing.
- **Сравнение:** partial; The candidate accurately states the termination/expiration exclusions but omits the agreement’s separate provision that neither party is liable for any special, consequential, or indirect damages, however caused. It adds an unrelated antecedent-obligations point.

### `cuad-aurasystemsinc_06_16_2010-ex-10.25-strat-warranty-duration`

- **Флаги:** решение моделью: partial
- **Вопрос:** What warranty period or deadline for reporting defects applies under the strategic alliance agreement between Aura Systems and Zanotti East?
- **Эталон:** At all times during the Term of this Agreement, Zanotti shall warrant the Products to purchasers of AETRU Systems in accordance with the terms of its standard warranty attached hereto as Exhibit "C" ("End User Warranty"), as such End User Warranty may be modified from time to time by Zanotti, provided however that at no time shall such End User Warranty provide for a warranty coverage period of less than thirty-six (36) months from the time of purchase by the initial end-user. Additionally, Zanotti shall offer to end-users the option to purchase extended warranty coverage for an additional twenty-four (24) months - making the total warranty period sixty (60) months.
- **Замечание модели:** —
- **Ответ модели по документу:** The End-User Warranty period is at least **thirty-six (36) months from the time of purchase by the initial end-user**. Zanotti must **immediately alert Aura** upon becoming aware of any defect in or hazard posed by a Product.
- **Сравнение:** partial; The candidate correctly states the minimum 36-month warranty period but omits that Zanotti must offer an additional 24 months of extended coverage, for a possible total of 60 months. It also adds an immediate defect/hazard alert obligation not stated in the reference.

### `cuad-bellringbrands_inc_02_07_2020-ex-10.18-m-expiration-date`

- **Флаги:** LLM-вердикт: suspect; вопрос неоднозначен
- **Вопрос:** What is the term of the master supply agreement between Premier Nutrition and Fonterra and when does it expire?
- **Эталон:** This Agreement will commence on the Effective Date and continue for an Initial Term of five (5) years, and will automatically renew for additional periods of five (5) years unless one Party notifies the other of its intention not to renew, no less than 12 months prior to the expiration of the then-current term, unless terminated as permitted under this Agreement.
- **Замечание модели:** The term and renewal provisions are fully supported, but the question identifies the parties as Premier Nutrition and Fonterra, while the excerpt identifies PNC and Supplier and does not establish those names. No specific expiration date can be determined without the Effective Date.
- **Ответ модели по документу:** The agreement has an initial term of five (5) years from the Effective Date and automatically renews for additional five (5)-year periods unless either party gives at least 12 months’ notice of non-renewal. The excerpts do not state the Effective Date, so the expiration date cannot be determined.
- **Сравнение:** yes; 

### `cuad-bellringbrands_inc_02_07_2020-ex-10.18-m-renewal-term`

- **Флаги:** LLM-вердикт: suspect; вопрос неоднозначен
- **Вопрос:** Does the master supply agreement between Premier Nutrition and Fonterra renew automatically, and for how long?
- **Эталон:** This Agreement will commence on the Effective Date and continue for an Initial Term of five (5) years, and will automatically renew for additional periods of five (5) years unless one Party notifies the other of its intention not to renew, no less than 12 months prior to the expiration of the then-current term, unless terminated as permitted under this Agreement.
- **Замечание модели:** The renewal terms are fully supported, but the question identifies Premier Nutrition and Fonterra while the excerpt identifies PNC/BellRing Brands and a Supplier; the parties/company identity is ambiguous or inconsistent.
- **Ответ модели по документу:** Yes. The agreement automatically renews for additional periods of five (5) years unless either party provides notice of non-renewal at least 12 months before the current term expires.
- **Сравнение:** yes; 

### `cuad-bioamberinc_04_10_2013-ex-10.34-developm-exclusivity`

- **Флаги:** решение моделью: partial
- **Вопрос:** What exclusivity obligations does the development agreement between Cargill and Bioamber establish?
- **Эталон:** Cargill hereby grants Bioamber, and Bioamber hereby accepts, an exclusive, royalty-free license to Cargill Improvements and Joint Improvements for use in the Field during the term of this Development Agreement with a reservation of right for Cargill to practice such Cargill Improvements and Joint Improvements for use in the field of succinic acid and salts thereof during the term of this Development Agreement. Bioamber hereby grants Cargill, and Cargill hereby accepts, an exclusive, worldwide, royalty-free license with an unlimited right to sublicense under and to Bioamber Improvements for use outside the Field during the term of this Development Agreement
- **Замечание модели:** —
- **Ответ модели по документу:** - Cargill grants Bioamber an **exclusive, royalty-free license** to Cargill Improvements and Joint Improvements for use in the Field during the term of the Development Agreement, limited to research purposes, with no sublicensing or “have made” rights. - Bioamber grants Cargill an **exclusive, worldwide, royalty-free license**, with an unlimited right to sublicense, under Bioamber Improvements for use outside the Field during the term, also limited to research purposes. - Bioamber owns Improvements in the field of succinic acid and salts thereof; Cargill owns Improvements in all other fields, 
- **Сравнение:** partial; The candidate captures the core reciprocal exclusive, royalty-free licenses, the Field/outside-Field scopes, duration, worldwide scope for Cargill, and Cargill’s unlimited sublicensing right. However, it adds unsupported limitations to research purposes and no sublicensing/'have made' rights, and adds ownership statements not present in the reference. It also omits Cargill’s reservation to practice the Improvements in the succinic acid and salts field.

### `cuad-bioamberinc_04_10_2013-ex-10.34-developm-non-compete`

- **Флаги:** решение моделью: partial
- **Вопрос:** What non-compete restrictions does the development agreement between Cargill and Bioamber impose?
- **Эталон:** Bioamber will not itself or with or through third parties engage in the development of biocatalysts other than E. coli for the production of succinic acid or salts thereof, except for the development activities under the terms and conditions of this Development Agreement. This restriction shall apply to any succinic acid biocatalyst other than E. coli, be it a biocatalyst developed in-house, licensed-in, or under development at a third party lab that is funded by Bioamber or to which Bioamber has secured a future right or right of first refusal through direct payment, in kind contribution, grant, gift, differed payment or commitment to a future payment.
- **Замечание модели:** —
- **Ответ модели по документу:** Bioamber may not, during the Term, itself or through third parties develop biocatalysts other than *E. coli* for producing succinic acid or its salts, except as permitted under the Development Agreement. It may evaluate other biocatalysts to identify alternative technologies, but must cease within 30 days all further funding and development—including genetic modification or fermentation-condition optimization—once a non-*E. coli* biocatalyst demonstrates production of succinic acid above [***] grams per liter. The restriction applies to biocatalysts developed in-house, licensed in, or under de
- **Сравнение:** partial; The candidate captures the core restriction and covered biocatalyst sources, but adds an evaluation/30-day funding-and-development exception and threshold not stated in the reference, and omits the reference’s broader wording about engaging "with or through" third parties and the specific ways future rights may be secured.

### `ru-arenda-novyi-srok`

- **Флаги:** решение моделью: partial
- **Вопрос:** Что будет, если арендатор продолжает пользоваться имуществом после окончания срока аренды, а арендодатель не возражает?
- **Эталон:** Договор считается возобновлённым на тех же условиях на неопределённый срок (п. 2 ст. 621 ГК РФ).
- **Замечание модели:** —
- **Ответ модели по документу:** Договор считается возобновленным на тех же условиях на неопределенный срок (статья 610).
- **Сравнение:** partial; Вывод совпадает, но неверно указана статья: это п. 2 ст. 621 ГК РФ, а не ст. 610.

### `ru-podryad-riski`

- **Флаги:** решение моделью: partial
- **Вопрос:** Кто несёт риск случайной гибели результата работы до его приёмки заказчиком?
- **Эталон:** Подрядчик, если иное не предусмотрено законом или договором; при просрочке передачи или приёмки — сторона, допустившая просрочку (ст. 705).
- **Замечание модели:** —
- **Ответ модели по документу:** Подрядчик.
- **Сравнение:** partial; Не указаны исключения: иное может быть предусмотрено законом или договором; при просрочке передачи или приёмки риск несёт сторона, допустившая просрочку.

### `ru-podryad-uklonenie-ot-priemki`

- **Флаги:** LLM-вердикт: suspect; фрагментов не хватает
- **Вопрос:** Что может сделать подрядчик, если заказчик уклоняется от приёмки выполненной работы?
- **Эталон:** По истечении месяца со дня, когда результат должен был быть передан, и после двукратного предупреждения заказчика подрядчик вправе продать результат работы, а выручку за вычетом своих платежей внести в депозит на имя заказчика (п. 6 ст. 720).
- **Замечание модели:** В доказательстве указано только право подрядчика действовать по истечении месяца; условия двукратного предупреждения, продажи результата и внесения выручки в депозит подтверждаются лишь отрывком документа, а не выделенным evidence.
- **Ответ модели по документу:** Если заказчик уклоняется от приёмки выполненной работы, подрядчик вправе по истечении месяца со дня, когда результат должен был быть передан заказчику, и после двукратного предупреждения заказчика продать результат работы. Вырученную сумму за вычетом причитающихся подрядчику платежей он должен внести на имя заказчика в депозит (п. 6 ст. 720 ГК РФ).
- **Сравнение:** yes; 

### `ru-yc-limit-otvetstvennosti`

- **Флаги:** решение моделью: partial
- **Вопрос:** Чем ограничен размер ответственности Яндекса перед клиентом Яндекс Облака?
- **Эталон:** Общей суммой платежей, полученных от клиента за последний отчётный период перед основанием ответственности; за упущенную выгоду и косвенные убытки Яндекс не отвечает (п. 10.1, 10.7 оферты).
- **Замечание модели:** —
- **Ответ модели по документу:** Предельный размер ответственности Яндекса за убытки и реальный ущерб ограничен общей суммой платежей, полученных от Клиента за последний Отчетный период, предшествующий основанию возникновения ответственности (п. 10.7 Оферты).
- **Сравнение:** partial; Не указано, что Яндекс не отвечает за упущенную выгоду и косвенные убытки (п. 10.1).

### `ru-yc-otkaz-klienta`

- **Флаги:** решение моделью: no
- **Вопрос:** За сколько дней клиент Яндекс Облака должен уведомить об одностороннем отказе от договора, а за сколько — Яндекс?
- **Эталон:** Клиент — не менее чем за 10 календарных дней (п. 12.1), Яндекс — не менее чем за 30 календарных дней (п. 12.9).
- **Замечание модели:** —
- **Ответ модели по документу:** Клиент должен уведомить Яндекс не менее чем за **10 (десять) календарных дней** до предполагаемой даты расторжения (п. 12.1). Для Яндекса установлен **немедленный** отказ с прекращением доступа к Сервисам в указанных случаях (п. 12.4).
- **Сравнение:** no; Кандидат правильно указал срок для клиента — 10 календарных дней, но не указал срок для Яндекса — не менее 30 календарных дней, вместо этого привел сведения о немедленном отказе по п. 12.4.

### `ru-yc-udalenie-dannyh`

- **Флаги:** LLM-вердикт: suspect; в документе есть противоречие
- **Вопрос:** Как долго Яндекс Облако хранит данные клиента после приостановки доступа и после прекращения договора?
- **Эталон:** После приостановки доступа — 60 календарных дней; после прекращения договора данные удаляются в течение 72 часов, если иной срок не предусмотрен законом (п. 12.5.1, 12.5.4).
- **Замечание модели:** Основные сроки подтверждены, однако после приостановки доступa документ предусматривает исключения: данные могут быть немедленно удалены после расторжения договора, а приостановление в пробный период допускает удаление в любое время. Кроме того, 60 дней — срок хранения при приостановлении при неустранении нарушений, а не безусловный срок.
- **Ответ модели по документу:** После приостановки доступа Яндекс хранит данные и Контент клиента **60 календарных дней**. Затем, если нарушение не устранено, они могут быть удалены **в течение 72 часов**. После прекращения договора данные помечаются как удаляемые и удаляются вместе с ресурсами платформы **в течение 72 часов с момента прекращения договора**, если иной срок не установлен применимым законодательством.
- **Сравнение:** yes; 

### `code-click-clirunner-exceptions`

- **Флаги:** числа не из фрагментов: 1, 1
- **Вопрос:** What exit code does CliRunner.invoke report when the command raises an unexpected exception, and how can I make the exception propagate?
- **Эталон:** exit_code is 1 and the exception is stored in `result.exception`; pass `catch_exceptions=False` to re-raise it. A SystemExit with a non-integer code is printed to stdout and also mapped to exit code 1.
- **Замечание модели:** —
- **Ответ модели по документу:** When the command raises an unexpected exception, `CliRunner.invoke` reports exit code `1`: ```python except Exception as e: if not catch_exceptions: raise exception = e exit_code = 1 ``` To make the exception propagate, call `invoke` with: ```python catch_exceptions=False ```
- **Сравнение:** yes; 

### `code-click-exception-hierarchy`

- **Флаги:** решение моделью: partial
- **Вопрос:** Which click exceptions are subclasses of UsageError?
- **Эталон:** BadParameter (and MissingParameter, which extends BadParameter), NoSuchOption, BadOptionUsage and BadArgumentUsage. FileError extends ClickException directly; Abort and Exit extend RuntimeError.
- **Замечание модели:** —
- **Ответ модели по документу:** BadParameter and MissingParameter.
- **Сравнение:** partial; The candidate omits NoSuchOption, BadOptionUsage, and BadArgumentUsage, which are also subclasses of UsageError.

### `code-click-max-content-width`

- **Флаги:** решение моделью: no
- **Вопрос:** What is the default maximum width of click help pages?
- **Эталон:** 80 characters: `max_content_width` defaults to 80 if not overridden, even if the terminal is wider; `terminal_width` is inherited from the parent or auto-detected.
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The candidate does not provide the default maximum width, which is 80 characters.

### `code-httpx-digest-algorithms`

- **Флаги:** числа не из фрагментов: 256, 256
- **Вопрос:** Which digest algorithms does httpx.DigestAuth support and what is the default?
- **Эталон:** MD5, MD5-SESS, SHA, SHA-SESS, SHA-256, SHA-256-SESS, SHA-512 and SHA-512-SESS; if the server challenge does not specify an algorithm, MD5 is used.
- **Замечание модели:** —
- **Ответ модели по документу:** httpx.DigestAuth supports: - MD5 - MD5-SESS - SHA (SHA-1) - SHA-SESS (SHA-1) - SHA-256 - SHA-256-SESS - SHA-512 - SHA-512-SESS The default algorithm is **MD5**, as `_parse_challenge()` uses `header_dict.get("algorithm", "MD5")`.
- **Сравнение:** yes; 

### `code-httpx-http2`

- **Флаги:** числа не из фрагментов: 2
- **Вопрос:** How do I enable HTTP/2 in httpx?
- **Эталон:** Install the optional extra with `pip install httpx[http2]` and create the client with `http2=True`, e.g. `httpx.AsyncClient(http2=True)`; HTTP/2 is off by default.
- **Замечание модели:** —
- **Ответ модели по документу:** Install the optional HTTP/2 dependencies: ```shell pip install httpx[http2] ``` Then instantiate a client with `http2=True`: ```python client = httpx.AsyncClient(http2=True) ``` HTTP/2 support is also available with `Client`.
- **Сравнение:** yes; 

### `code-httpx-raise-for-status`

- **Флаги:** числа не из фрагментов: 1, 3, 4, 5
- **Вопрос:** What does Response.raise_for_status() do for a 2xx response and for an error, and when does it raise RuntimeError?
- **Эталон:** For a success status it returns the response itself (so calls can be chained); for 1xx/3xx/4xx/5xx it raises HTTPStatusError with a message like "Client error ..."; it raises RuntimeError if the request instance has not been set on the response.
- **Замечание модели:** —
- **Ответ модели по документу:** For a 2xx response, `Response.raise_for_status()` returns the response unchanged. For an error, it raises `HTTPStatusError` with a message containing the status code, reason phrase, URL, and—if applicable—the redirect location and a status-information URL. It raises `RuntimeError` when the response has no associated request (`self._request is None`).
- **Сравнение:** yes; 

### `code-httpx-retries`

- **Флаги:** числа не из фрагментов: 503
- **Вопрос:** Does httpx retry failed requests, and which errors are retried?
- **Эталон:** Not by default (`retries: int = 0` in HTTPTransport). With `httpx.HTTPTransport(retries=N)` only connection failures — ConnectError and ConnectTimeout — are retried; for read/write errors or 503 the docs suggest tools like tenacity.
- **Замечание модели:** —
- **Ответ модели по документу:** Yes. When using `httpx.HTTPTransport(retries=1)`, httpx retries requests once when an `httpx.ConnectError` or `httpx.ConnectTimeout` occurs. The default is `retries=0`; other errors, such as read/write errors or `503 Service Unavailable`, are not retried by this mechanism.
- **Сравнение:** yes; 

### `code-httpx-ssl-cert-env`

- **Флаги:** LLM-вердикт: suspect; в документе есть противоречие
- **Вопрос:** Does httpx 0.28 use the SSL_CERT_FILE environment variable?
- **Эталон:** In code, yes: `create_ssl_context` with `verify=True` and `trust_env=True` (the default) loads SSL_CERT_FILE or SSL_CERT_DIR if set, otherwise certifi. Note that the SSL documentation page still says that httpx does not pull these variables in automatically.
- **Замечание модели:** The code supports use of SSL_CERT_FILE (and SSL_CERT_DIR) when verify=True and trust_env=True, with certifi otherwise. However, the documentation excerpt explicitly states that httpx does not automatically pull in these variables and requires explicit enabling, contradicting or materially qualifying the reference answer.
- **Ответ модели по документу:** Yes. When `trust_env=True` (the default) and `verify=True`, httpx 0.28 uses `SSL_CERT_FILE` if it is set.
- **Сравнение:** yes; 

### `finqa-aapl_2003_page_48.pdf-1`

- **Флаги:** эталон есть ещё в 1 док.
- **Вопрос:** According to the 2003 annual report of Apple, excluding accretion , what was the ending balance of asset retirement liability as of september 27 2003 , in millions?
- **Эталон:** 6
- **Эталон также в:** tables/finqa/AAPL_2004_page_68.docx
- **Замечание модели:** —
- **Ответ модели по документу:** $6.0 million ($7.2 million − $1.2 million accretion).
- **Сравнение:** yes; 

### `finqa-abc_2005_page_49.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2005 annual report of AmerisourceBergen, without employee severance costs in 2004 and 2005 , what would have been the increase in net income in millions?\\n\\n
- **Эталон:** 18.7
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The reference answer is 18.7 million, but the candidate does not provide an answer.

### `finqa-abmd_2005_page_29.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2005 annual report of Abiomed, assuming the same rate of growth as in 2005 , what would the projected risk free interest rate be in 2006?
- **Эталон:** 5.38%
- **Замечание модели:** —
- **Ответ модели по документу:** Risk-free interest rate growth from 2004 to 2005: \[ \frac{3.87\%-2.56\%}{2.56\%}=51.17\% \] Projected 2006 rate: \[ 3.87\%\times(1+51.17\%)\approx5.85\% \] The projected risk-free interest rate would be **5.85%**.
- **Сравнение:** no; The candidate gives 5.85%, whereas the reference answer is 5.38%.

### `finqa-amat_2013_page_37.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2013 annual report of Applied Materials, what is the total return if 100000 are invested in applied materials in 2008 and sold in 2011?
- **Эталон:** 18210
- **Замечание модели:** —
- **Ответ модели по документу:** Applied Materials’ value increased from 100.00 in 2008 to 118.21 in 2011. Total return = \(100000 \times \frac{118.21}{100.00} = 118210\) Total return: **118210**
- **Сравнение:** no; The reference answer is 18210, while the candidate gives 118210; it reports the ending value rather than the total return.

### `finqa-amt_2003_page_102.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2003 annual report of American Tower, what portion of the redemption amount of 6.25% ( 6.25 % ) notes was in accrued interest?
- **Эталон:** 2.2%
- **Замечание модели:** —
- **Ответ модели по документу:** $4.8 million.
- **Сравнение:** no; The reference gives the accrued interest portion as 2.2%, while the candidate gives a dollar amount of $4.8 million.

### `finqa-awk_2012_page_117.pdf-1`

- **Флаги:** LLM-вердикт: wrong; ответ не следует из фрагментов; в документе есть противоречие
- **Вопрос:** According to the 2012 annual report of American Water Works, what was total liability reflected as other long-term liabilities in the accompanying consolidated balance sheets for december 31 , 2012 and 2011 in millions?
- **Эталон:** 121321
- **Замечание модели:** The evidence states $74,360 and $46,961 for 2012 and 2011, respectively. Their total is $121,321, but the question asks for the liability for each year, not their sum; the reference answer omits the year-specific amounts.
- **Ответ модели по документу:** ($74,360 + $46,961) ÷ 1,000 = **$121.321 million**.
- **Сравнение:** yes; 

### `finqa-bll_2006_page_67.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2006 annual report of Ball Corporation, current assets were what percent of net assets acquired for the can and alcan transactions?
- **Эталон:** 32.2%
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The reference states that current assets were 32.2% of net assets acquired, but the candidate does not provide an answer.

### `finqa-ce_2009_page_65.pdf-2`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2009 annual report of Celanese, for the 2010 currency maturities , what would the value be without the euro maturities , in us$ millions?
- **Эталон:** -305
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The candidate does not provide the required value of -305 US$ million.

### `finqa-cme_2010_page_123.pdf-1`

- **Флаги:** LLM-вердикт: wrong; ответ не следует из фрагментов
- **Вопрос:** According to the 2010 annual report of CME Group, whats is the percentage of equity compensation plans that were not approved by security holders?
- **Эталон:** 0.491%
- **Замечание модели:** The evidence gives 5,978 securities in plans not approved by security holders and 1,217,121 total securities. Their percentage is approximately 0.492%, not 0.491%.
- **Ответ модели по документу:** \[ \frac{5,978}{1,217,121}\times 100 = 0.49\% \] The percentage was **0.49%**.
- **Сравнение:** yes; 

### `finqa-disca_2011_page_49.pdf-1`

- **Флаги:** LLM-вердикт: wrong; ответ не следует из фрагментов
- **Вопрос:** According to the 2011 annual report of Discovery Communications, what was the percentage cumulative total shareholder return on disca from september 18 , 2008 to december 31 , 2011?
- **Эталон:** 196.67
- **Замечание модели:** The table shows DISCA rising from $100 invested on September 18, 2008 to $296.67 on December 31, 2011, implying a cumulative total return of 196.67%, not merely unsupported as stated; however, the reference answer matches this calculation. The supplied evidence does not explicitly state the calculated percentage, so under the strict claim-following criterion the answer is not directly supported.
- **Ответ модели по документу:** \[ \frac{296.67-100}{100}\times 100\%=196.67\% \] The percentage cumulative total shareholder return on DISCA was **196.67%**.
- **Сравнение:** yes; 

### `finqa-dxc_2018_page_56.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2018 annual report of DXC Technology, in fiscal 2018 what percentage of total costs and expenses was costs of services ( excludes depreciation and amortization and restructuring costs ) ?
- **Эталон:** 78%
- **Замечание модели:** —
- **Ответ модели по документу:** 73.0%
- **Сравнение:** no; The candidate gives 73.0%, while the reference answer is 78%.

### `finqa-ecl_2016_page_52.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2016 annual report of Ecolab, what portion of cash and cash equivalents on hand are held in u.s . as of december 31 , 2016?
- **Эталон:** 43.7%
- **Замечание модели:** —
- **Ответ модели по документу:** $327 million − $184 million = **$143 million** held in the U.S.
- **Сравнение:** no; The reference asks for the portion as a percentage (43.7%), while the candidate gives a dollar amount ($143 million) and does not provide the required percentage.

### `finqa-emr_2017_page_78.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2017 annual report of Emerson Electric, at the pace of 2017 how many years of issuance remain for the restricted stock plan for non-management directors?
- **Эталон:** 8.6
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The reference answer is 8.6 years, but the candidate states the information is not in the document.

### `finqa-fbhs_2017_page_22.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2017 annual report of Fortune Brands Home & Security, in 2017 what was the ratio of the cabinets sales to the doors
- **Эталон:** 4.9
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The candidate does not provide the ratio; the reference answer is 4.9.

### `finqa-fis_2006_page_31.pdf-1`

- **Флаги:** решение моделью: no
- **Вопрос:** According to the 2006 annual report of Fidelity National Information Services, what portion of the total leased locations are in texas?
- **Эталон:** 13.2%
- **Замечание модели:** —
- **Ответ модели по документу:** Texas leased locations portion = \( \frac{19}{57+26+22+19+9+8+7+63+81} = \frac{19}{292} \approx 6.5\% \).
- **Сравнение:** no; The reference answer is 13.2%, while the candidate calculates 6.5%.

### `finqa-gs_2012_page_121.pdf-1`

- **Флаги:** LLM-вердикт: wrong; ответ не следует из фрагментов; фрагментов не хватает; решение моделью: no
- **Вопрос:** According to the 2012 annual report of Goldman Sachs, what is the percentage change in total assets in 2012?
- **Эталон:** 1.7%
- **Замечание модели:** The reference answer concerns the percentage change in Total assets, requiring $938,555 (2012) and $923,225 (2011), which are present in the document excerpt but absent from the supplied evidence fragment. Using those values gives approximately 1.7%, so the answer is numerically supported by the excerpt, not by the provided evidence.
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; The reference states that total assets increased by 1.7% in 2012, while the candidate says the information is not in the document.

### `finqa-hii_2015_page_121.pdf-1`

- **Флаги:** LLM-вердикт: wrong; ответ не следует из фрагментов; фрагментов не хватает
- **Вопрос:** According to the 2015 annual report of Huntington Ingalls Industries, what is the net income margin in the q1 of 2014?
- **Эталон:** 5.6%
- **Замечание модели:** The evidence provides Q1 2014 net earnings ($90 million) and sales and service revenues ($1,594 million), but does not support a 5.6% net income margin. Net earnings divided by revenues is approximately 5.6%, so the answer requires arithmetic using a value present only in the document excerpt, not the provided evidence fragment.
- **Ответ модели по документу:** Net income margin = Net earnings ÷ Sales and service revenues = $90 million ÷ $1,594 million = 0.0565 ≈ **5.65%**
- **Сравнение:** yes; 

### `ru-cross-chistaya-pribyl-2025`

- **Флаги:** решение моделью: no
- **Вопрос:** У какой компании чистая прибыль за 2025 год больше — у Мосбиржи или у МТС (прибыль, относящаяся к акционерам)?
- **Эталон:** У Мосбиржи: 59 390,7 млн руб. против примерно 35,2 млрд руб. у МТС.
- **Замечание модели:** —
- **Ответ модели по документу:** У МТС: 35 219.96743109303 против 16 333 у Мосбиржи.
- **Сравнение:** no; Кандидат неверно указал компанию и сумму прибыли Мосбиржи: по эталону у Мосбиржи 59 390,7 млн руб., что больше примерно 35,2 млрд руб. у МТС.

### `ru-moex-chistaya-pribyl-2025`

- **Флаги:** решение моделью: no
- **Вопрос:** Какой была чистая прибыль Московской биржи по МСФО за 2025 год?
- **Эталон:** 59 390,7 млн руб. (в 2024 году — 79 247,6 млн руб.).
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; В ответе кандидата отсутствует значение чистой прибыли; по справке — 59 390,7 млн руб. за 2025 год.

### `ru-moex-dividendy-2021`

- **Флаги:** решение моделью: no
- **Вопрос:** В каком году Мосбиржа не выплачивала дивиденды по данным databook?
- **Эталон:** За 2021 год: дивиденды на акцию равны 0 и коэффициент дивидендных выплат равен 0.
- **Замечание модели:** —
- **Ответ модели по документу:** В 2020 году: дивиденды на акцию (DPS) — 0.
- **Сравнение:** no; В справочном ответе указан 2021 год, а кандидат указывает 2020 год.

### `ru-moex-ebitda-2023`

- **Флаги:** решение моделью: no
- **Вопрос:** Какой была EBITDA Московской биржи в 2023 году?
- **Эталон:** 82 231,2 млн руб. (скорректированная EBITDA — 80 862,7 млн руб.).
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; Кандидат не содержит значения EBITDA Московской биржи за 2023 год.

### `ru-moex-komissionnye-dohody`

- **Флаги:** числа не из фрагментов: 24,9; решение моделью: no
- **Вопрос:** Как изменились комиссионные доходы Московской биржи в 2025 году по сравнению с 2024?
- **Эталон:** Выросли с 62 983,4 до 78 655,3 млн руб., примерно на 24,9%.
- **Замечание модели:** —
- **Ответ модели по документу:** Комиссионные доходы выросли с 64 497,5 млн руб. в 2024 году до 74 836,4 млн руб. в 2025 году: 74 836,4 − 64 497,5 = 10 338,9 млн руб. (+16,0%).
- **Сравнение:** no; Указаны другие значения и темп роста: в эталоне 62 983,4 → 78 655,3 млн руб. (примерно +24,9%), а в ответе 64 497,5 → 74 836,4 млн руб. (+16,0%).

### `ru-moex-pdf-sredstva-klientov`

- **Флаги:** числа не из фрагментов: 31.12, 958351,7, 30.06
- **Вопрос:** Как изменились средства клиентов Мосбиржи за первое полугодие 2026 года?
- **Эталон:** Снизились с 1 179 680,4 млн руб. на 31.12.2025 до 958 351,7 млн руб. на 30.06.2026.
- **Замечание модели:** —
- **Ответ модели по документу:** Средства клиентов уменьшились на 221 328,7 млн руб.: с 1 179 680,4 млн руб. на 31 декабря 2025 года до 958 351,7 млн руб. на 30 июня 2026 года.
- **Сравнение:** yes; 

### `ru-moex-personal-2025`

- **Флаги:** числа не из фрагментов: 9,5; решение моделью: no
- **Вопрос:** Сколько Мосбиржа потратила на персонал в 2025 году и как это соотносится с 2024?
- **Эталон:** 22 739,9 млн руб. в 2025 году против 25 128,8 млн руб. в 2024 году — расходы снизились примерно на 9,5%.
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; В ответе отсутствуют данные о расходах на персонал: 22 739,9 млн руб. в 2025 году против 25 128,8 млн руб. в 2024 году, снижение примерно на 9,5%.

### `ru-moex-reklama`

- **Флаги:** числа не из фрагментов: 5,5; решение моделью: no
- **Вопрос:** Во сколько раз выросли расходы Мосбиржи на рекламу и маркетинг с 2023 по 2025 год?
- **Эталон:** Примерно в 5,5 раза: с 1 808,7 до 9 863,5 млн руб.
- **Замечание модели:** —
- **Ответ модели по документу:** NOT IN DOCUMENT.
- **Сравнение:** no; В ответе кандидата отсутствует информация о росте расходов: примерно в 5,5 раза, с 1 808,7 до 9 863,5 млн руб.

### `ru-mts-capex-2025`

- **Флаги:** числа не из фрагментов: 14,9
- **Вопрос:** Сколько МТС потратила на капитальные затраты (CAPEX) в 2025 году и какая это доля выручки?
- **Эталон:** Около 120,6 млрд руб., примерно 14,9% выручки (в 2024 году — 132,4 млрд руб.).
- **Замечание модели:** —
- **Ответ модели по документу:** Капитальные затраты МТС в 2025 году составили **120,6 млрд руб.** Доля выручки: **120,6 / 807,2 × 100% ≈ 14,9%**
- **Сравнение:** yes; 

### `ru-mts-pogashenie-dolga`

- **Флаги:** решение моделью: no
- **Вопрос:** Сколько долга МТС предстоит погасить в 2026 году по графику на 31 декабря 2025?
- **Эталон:** Около 379,2 млрд руб. (в 2027 году — 195,6 млрд руб., в 2028 — 139,0 млрд руб.).
- **Замечание модели:** —
- **Ответ модели по документу:** 195.571490190673 млрд руб.
- **Сравнение:** no; В 2026 году предстоит погасить около 379,2 млрд руб.; 195,6 млрд руб. относится к 2027 году.

### `ru-mts-roznica-magaziny`

- **Флаги:** решение моделью: partial
- **Вопрос:** Как менялось число розничных магазинов МТС с конца 2023 по конец 2025 года?
- **Эталон:** Сократилось с 4 478 на конец 2023 года до 4 214 на конец 2024 и 3 914 на конец 2025.
- **Замечание модели:** —
- **Ответ модели по документу:** С конца 2023 года число розничных магазинов МТС уменьшилось с 4 478 до 3 914 к концу 2025 года. Расчёт: 3 914 − 4 478 = −564 магазина, или −12,6%.
- **Сравнение:** partial; Не указано промежуточное значение на конец 2024 года — 4 214 магазинов.

### `ru-mts-vyruchka-2025`

- **Флаги:** числа не из фрагментов: 14,7
- **Вопрос:** Какой была общая выручка Группы МТС за 2025 год?
- **Эталон:** 807 186 млн руб. (около 807,2 млрд руб.), рост на 14,7% к 2024 году.
- **Замечание модели:** —
- **Ответ модели по документу:** Общая выручка Группы МТС за 2025 год составила **807,2 млрд руб.** (или **807186 млн руб.**).
- **Сравнение:** yes; 
