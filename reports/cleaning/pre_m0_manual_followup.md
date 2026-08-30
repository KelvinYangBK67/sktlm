# pre-M₀ manual follow-up audit

本報告是對 frozen canonical data/canonical/gretil_iast 的逐文件只讀檢查。只記錄 positive/mechanical matches；|、||、短 token、相鄰元音與孤立字母均不是自動刪除判定。上下文以 ⟦...⟧ 標示最小 matched span。

## 檢查口徑

- 行號為 canonical txt 的 1-based physical line number；TSV 每個 match 一列。
- internal_single_danda 僅指同一行中 | 前後都有非空文字；line_end_single_danda 指最後一個非空字元為單一 |；double_danda 每個 || occurrence 計一次。這些是位置分類，不是錯誤判定。
- 孤立單字母以 IAST letter token 邊界機械比對；相鄰元音為 maximal vowel run，僅豁免 exact ai、au。兩者均可能是正文。
- apostrophe 只有在左側（略過 ASCII spaces）為 e/o、右側緊接 lowercase IAST 且不跨 danda 時視為通過；本欄只列未通過者。
- 英文、藏語與 Roman numeral count 是明列 conservative diagnostic patterns 的 occurrence 數，不宣稱完整語言辨識。

## 3_purana/sivap1_u.txt

**人工提示**

- chapter

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_chapter | 25 | editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 0 |
| adjacent_vowels_non_ai_au | 0 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- manual_chapter — 25 occurrence(s); editorial
  - line 17: chapter — ⟦chapter⟧
  - line 177: chapter — ⟦chapter⟧
  - line 451: chapter — ⟦chapter⟧

**同文件中的同類／相關可疑項**

- 未由本輪 conservative patterns 找到額外同類；不等於已通過語義 adjudication。

## 3_purana/sivap7_u.txt

**人工提示**

- chapter

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_chapter | 76 | editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 2 |
| isolated_single_consonant | 0 |
| adjacent_vowels_non_ai_au | 2 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 2 occurrence(s); 看起來像正文 / 不確定
  - line 3251: aṛ — anye ca rāj⟦aṛ⟧ṣayo nānāvīryasamanvitā \|\|
  - line 3823: aṛ — sudarbh⟦aṛ⟧tusaṃstīrṇaṃ susamiddhahutāśanam \|\|
- isolated_single_vowel — 2 occurrence(s); 不確定
  - line 15509: a — ⟦a⟧ u meti trimātrābhiḥ parastāccārdhamātrayā \|\|
  - line 15509: u — a ⟦u⟧ meti trimātrābhiḥ parastāccārdhamātrayā \|\|
- manual_chapter — 76 occurrence(s); editorial
  - line 11: chapter — ⟦chapter⟧
  - line 293: chapter — ⟦chapter⟧
  - line 431: chapter — ⟦chapter⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_vowel (2)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/srabhu_u.txt

**人工提示**

- 藏語轉寫殘留
- Roman numerals

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| tibetan_transcription_candidate | 626 | 不確定（高度疑似藏語轉寫） |
| roman_numeral_candidate | 121 | source-specific separator / editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 500 |
| standalone_danda_line | 29 |
| line_start_single_danda | 250 |
| line_start_double_danda | 14 |
| isolated_single_vowel | 96 |
| isolated_single_consonant | 40 |
| adjacent_vowels_non_ai_au | 165 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 165 occurrence(s); 看起來像正文 / 不確定
  - line 13: ao — \| smras pa \| rkyen gñis te \|\| gtso bo daṅ dman p⟦ao⟧ \|\|
  - line 33: ii — \| ⟦ii⟧
  - line 37: iii — \| ⟦iii⟧
- isolated_single_consonant — 40 occurrence(s); apparatus / source-specific separator / 不確定
  - line 47: v — \| ⟦v⟧
  - line 75: v — \| ⟦v⟧
  - line 469: v — \| ⟦v⟧
- isolated_single_vowel — 96 occurrence(s); 不確定
  - line 5: i — …es su bstan pa rñed ciṅ rgyu de dag kyaṅ med par gyur pa \| de'⟦i⟧ tshe na dge bai rtsa ba dag yoṅs su smin ciṅ rim gyis yoṅs su…
  - line 29: i — \| ⟦i⟧
  - line 57: i — \| ⟦i⟧
- line_start_double_danda — 14 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 5: \|\| — ⟦\|\|⟧ de dag kyaṅ gaṅ gi tshe saṅs rgyas byuṅ ba daṅ dam pai chos ṅ…
  - line 41: \|\| — ⟦\|\|⟧ iv
  - line 287: \|\| — ⟦\|\|⟧ yoṅs su mya ṅan las da ba daṅ yaṅ dag pa ñid du ṅes pa la jug…
- line_start_single_danda — 250 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 13: \| — ⟦\|⟧ smras pa \| rkyen gñis te \|\| gtso bo daṅ dman pao \|\|
  - line 17: \| — ⟦\|⟧ smras pa \| di lta ste \|\|
  - line 21: \| — ⟦\|⟧ smras pa \| rkyen dman pa ni maṅ ste \| di lta ste \| ātmasampat…
- multiple_blank_lines — 500 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: riṅ ba yin te \|\|
  - line 10: 3 consecutive blank lines — previous:  du yoṅs su mya ṅan las da bai skal ba med pa kho na yin no \|\| ⟦3 consecutive blank lines⟧ next: \| smras pa \| rkyen gñis te \|\| gtso bo daṅ dman pao \|\|
  - line 14: 3 consecutive blank lines — previous: \| smras pa \| rkyen gñis te \|\| gtso bo daṅ dman pao \|\| ⟦3 consecutive blank lines⟧ next: \| smras pa \| di lta ste \|\|
- roman_numeral_candidate — 121 occurrence(s); source-specific separator / editorial
  - line 29: i — \| ⟦i⟧
  - line 33: ii — \| ⟦ii⟧
  - line 37: iii — \| ⟦iii⟧
- standalone_danda_line — 29 occurrence(s); source-specific separator / 不確定
  - line 115: \|\| — ⟦\|\|⟧
  - line 215: \|\| — ⟦\|\|⟧
  - line 223: \|\| — ⟦\|\|⟧
- tibetan_transcription_candidate — 626 occurrence(s); 不確定（高度疑似藏語轉寫）
  - line 5: byuṅ — \|\| de dag kyaṅ gaṅ gi tshe saṅs rgyas ⟦byuṅ⟧ ba daṅ dam pai chos ṅan pa daṅ rjes su mthun pai gdams ṅag rj…
  - line 5: chos — \|\| de dag kyaṅ gaṅ gi tshe saṅs rgyas byuṅ ba daṅ dam pai ⟦chos⟧ ṅan pa daṅ rjes su mthun pai gdams ṅag rjes su bstan pa rñed …
  - line 5: ciṅ — … ṅan pa daṅ rjes su mthun pai gdams ṅag rjes su bstan pa rñed ⟦ciṅ⟧ rgyu de dag kyaṅ med par gyur pa \| de'i tshe na dge bai rtsa …

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (40)、isolated_single_vowel (96)、line_start_double_danda (14)、line_start_single_danda (250)、multiple_blank_lines (500)、standalone_danda_line (29)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/udanav_u.txt

**人工提示**

- 行中 single |、句末 |、||

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| internal_single_danda | 13798 | 看起來像正文 boundary / 不確定 |
| line_end_single_danda | 1121 | 看起來像正文 boundary / 不確定 |
| double_danda | 1174 | 看起來像正文 boundary / 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 122 |
| line_start_single_danda | 1 |
| line_start_double_danda | 12 |
| isolated_single_vowel | 1 |
| isolated_single_consonant | 2 |
| adjacent_vowels_non_ai_au | 3 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 3 occurrence(s); 看起來像正文 / 不確定
  - line 157: ūu — kim \| anena \| śarīreṇa \| sravatā \| p⟦ūu⟧tinā \| sadā \|
  - line 835: īi — na \| tu \| bhuñj⟦īi⟧ta \| duhśīlo \| rāṣṭra \| piṇḍam \| asamyataḥ \|\|
  - line 1277: ua — rājā \| iva \| rāṣṭram \| vipl⟦ua⟧m \| prahāya \| ekaś \| caren \| na \| ca \| pāpāni \| kuryāt \|\|
- double_danda — 1174 occurrence(s); 看起來像正文 boundary / 不確定
  - line 5: \|\| — stīnam \| iddham \| vinodya \| iha \| sampraharṣya \| ca \| mānasam ⟦\|\|⟧ stīnamiddham \|
  - line 7: \|\| — śṛṇuta \| imam \| pravakṣyāmi udānam \| jina \| bhāṣitam ⟦\|\|⟧
  - line 11: \|\| — anukampakena \| ṛṣiṇā śarīra \| antima \| dhāriṇā ⟦\|\|⟧
- internal_single_danda — 13798 occurrence(s); 看起來像正文 boundary / 不確定
  - line 1: \| — anitya ⟦\|⟧ varga
  - line 5: \| — stīnam ⟦\|⟧ iddham \| vinodya \| iha \| sampraharṣya \| ca \| mānasam \|\| stīna…
  - line 5: \| — stīnam \| iddham ⟦\|⟧ vinodya \| iha \| sampraharṣya \| ca \| mānasam \|\| stīnamiddham \|
- isolated_single_consonant — 2 occurrence(s); apparatus / source-specific separator / 不確定
  - line 35: n — daharā \| api \| ṃriyante \| hi \| narā \| nāryaś \| ca \| ⟦n⟧ \| ekaśaḥ \|\| anekaśaḥ \|
  - line 3893: v — anihsṛtān \| bhavā \| sarvāṃs \| tān \| vadāmi \| sadā \| ⟦v⟧ \| aham \|\|
- isolated_single_vowel — 1 occurrence(s); 不確定
  - line 4365: u — \|\| ⟦u⟧ \|\| brāhmaṇam \| tam \| bravīmy \| aham \|\|
- line_end_single_danda — 1121 occurrence(s); 看起來像正文 boundary / 不確定
  - line 5: \| — …\| vinodya \| iha \| sampraharṣya \| ca \| mānasam \|\| stīnamiddham ⟦\|⟧
  - line 9: \| — evam \| uktam \| bhagavatā \| sarva \| abhijñena \| tāyinā ⟦\|⟧
  - line 13: \| — anityā \| bata \| saṃskārā \| utpāda \| vyaya \| dharmiṇaḥ ⟦\|⟧
- line_start_double_danda — 12 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 59: \|\| — ⟦\|\|⟧ ghatano \| bhavati \| evam \| martyasya \| jīvitam \|\|
  - line 77: \|\| — ⟦\|\|⟧ jīvitam \| ca \| uparudhyate \|
  - line 1631: \|\| — ⟦\|\|⟧ naram \|
- line_start_single_danda — 1 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 3: \| — ⟦\|⟧ siddham
- standalone_danda_line — 122 occurrence(s); source-specific separator / 不確定
  - line 79: \|\| — ⟦\|\|⟧
  - line 91: \|\| — ⟦\|\|⟧
  - line 137: \|\| — ⟦\|\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (2)、isolated_single_vowel (1)、line_start_double_danda (12)、line_start_single_danda (1)、standalone_danda_line (122)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/vinsutru.txt

**人工提示**

- 藏語轉寫、英文
- 行首 |、行末 |

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| tibetan_transcription_candidate | 8 | 不確定（高度疑似藏語轉寫） |
| english_residue | 3 | editorial |
| line_start_single_danda | 5635 | source-specific separator / 看起來像正文 boundary |
| line_end_single_danda | 5905 | 看起來像正文 boundary / 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 9 |
| standalone_danda_line | 14 |
| line_start_single_danda | 5635 |
| line_start_double_danda | 307 |
| isolated_single_vowel | 31 |
| isolated_single_consonant | 39 |
| adjacent_vowels_non_ai_au | 19 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 19 occurrence(s); 看起來像正文 / 不確定
  - line 5: io — \| vastu \| chapter \| sect⟦io⟧n
  - line 609: ṛā — \| māt⟦ṛā⟧pitṛglānāṃś cāgārikam api \|
  - line 1673: aa — \| yuktakule cen nirākṛtaprayogatvaṃ par⟦aa⟧sya \|
- english_residue — 3 occurrence(s); editorial
  - line 5: chapter — \| vastu \| ⟦chapter⟧ \| section
  - line 5: section — \| vastu \| chapter \| ⟦section⟧
  - line 7: line — vin n \| n \| vastu \| ⟦line⟧
- isolated_single_consonant — 39 occurrence(s); apparatus / source-specific separator / 不確定
  - line 3: n — vin ⟦n⟧ \|\| vastu
  - line 7: n — vin ⟦n⟧ \| n \| vastu \| line
  - line 7: n — vin n \| ⟦n⟧ \| vastu \| line
- isolated_single_vowel — 31 occurrence(s); 不確定
  - line 13: a — ⟦a⟧ ka ras bris ga vinayasūtram guṇaprabha
  - line 43: ā — \| kañcit pariśuddhya tīti pṛṣṭvā śuddham ⟦ā⟧ rocayet \|
  - line 79: u — \| abhyupagatāv ⟦u⟧ pādhyāyasya yājñāyāṃ tad udbhūti \|
- line_end_single_danda — 5905 occurrence(s); 看起來像正文 boundary / 不確定
  - line 19: \| — vinayasūtram ⟦\|⟧
  - line 25: \| — \|\| namo buddhāya ⟦\|⟧
  - line 27: \| — \| atha niryāṇavṛttaṃ ⟦\|⟧
- line_start_double_danda — 307 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 11: \|\| — ⟦\|\|⟧ shri la
  - line 25: \|\| — ⟦\|\|⟧ namo buddhāya \|
  - line 99: \|\| — ⟦\|\|⟧ śrāmaṇeratvopanayavidhiḥ \|\|
- line_start_single_danda — 5635 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 5: \| — ⟦\|⟧ vastu \| chapter \| section
  - line 27: \| — ⟦\|⟧ atha niryāṇavṛttaṃ \|
  - line 29: \| — ⟦\|⟧ sarvasmin sannipatite saṃghe kṛtedaṃ veṣaṃ nipatya pragṛhītāñ…
- multiple_blank_lines — 9 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: vin n \|\| vastu
  - line 8: 3 consecutive blank lines — previous: vin n \| n \| vastu \| line ⟦3 consecutive blank lines⟧ next: \|\| shri la
  - line 20: 3 consecutive blank lines — previous: vinayasūtram \| ⟦3 consecutive blank lines⟧ next: śrāmaṇeratvopanayam
- standalone_danda_line — 14 occurrence(s); source-specific separator / 不確定
  - line 1125: \|\| — ⟦\|\|⟧
  - line 1353: \| — ⟦\|⟧
  - line 7890: \| — ⟦\|⟧
- tibetan_transcription_candidate — 8 occurrence(s); 不確定（高度疑似藏語轉寫）
  - line 11: shri la — \|\| ⟦shri la⟧
  - line 13: a ka ras bris ga — ⟦a ka ras bris ga⟧ vinayasūtram guṇaprabha
  - line 12782: dpal ldan vyri krama śi lar dpye — gnur chos kyi grags pas bris pa \| ⟦dpal ldan vyri krama śi lar dpye⟧ 'sla ra va la

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (39)、isolated_single_vowel (31)、line_start_double_danda (307)、multiple_blank_lines (9)、standalone_danda_line (14)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/vinv01_u.txt

**人工提示**

- 行首 ||
- 孤立單字母／單輔音

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| line_start_double_danda | 212 | source-specific separator / 看起來像正文 boundary |
| isolated_single_vowel | 3 | 不確定 |
| isolated_single_consonant | 3 | apparatus / source-specific separator / 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 10 |
| standalone_danda_line | 1 |
| line_start_single_danda | 0 |
| line_start_double_danda | 212 |
| isolated_single_vowel | 3 |
| isolated_single_consonant | 3 |
| adjacent_vowels_non_ai_au | 1 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 1 occurrence(s); 看起來像正文 / 不確定
  - line 491: ae — … gāthā bhāṣata ity eka upasaṃkrānto dvitīyas tṛtīyo yāvat sarv⟦ae⟧ 'nte upasaṃkrāntāḥ \| tathā ca tayā devatayā adhiṣṭhitā yathā …
- isolated_single_consonant — 3 occurrence(s); apparatus / source-specific separator / 不確定
  - line 25: m — \|\| ṭ \| ⟦m⟧ iti \| sa kathayati deva so 'pi rājā kṣatriyo mūrdhābhiṣikto v…
  - line 25: ṭ — \|\| ⟦ṭ⟧ \| m iti \| sa kathayati deva so 'pi rājā kṣatriyo mūrdhābhiṣik…
  - line 423: r — \|\| ⟦r⟧ lokadharmair anupaliptānām āryāṣṭāṅgamārgadaiśikānāṃ navāghāt…
- isolated_single_vowel — 3 occurrence(s); 不確定
  - line 153: a — …m anuprayacchāma iti \| sā kathayati kasmād asya dīyate \| etāv ⟦a⟧ \|
  - line 419: i — \|\| ⟦i⟧ \| i \|\| ādvayānāṃ trimalaprahīṇānāṃ tridamathavastukuśalānāṃ v…
  - line 419: i — \|\| i \| ⟦i⟧ \|\| ādvayānāṃ trimalaprahīṇānāṃ tridamathavastukuśalānāṃ vidyā…
- line_start_double_danda — 212 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 1: \|\| — ⟦\|\|⟧ nāmadheyāni vyavasthāpitāni \| biṃbisāraḥ kumāro 'ṣṭābhyo dhāt…
  - line 3: \|\| — ⟦\|\|⟧ upakaraṇaviśeṣair āśur vardhate hradastham iva paṅkajam \|\| ya…
  - line 5: \|\| — ⟦\|\|⟧ pṛthagbhavanti śilpasthānakarmasthānāni \| tadyathā hastigrīvā…
- multiple_blank_lines — 10 occurrence(s); editorial / mechanical
  - line 470: 3 consecutive blank lines — previous: nāsya kenacid vacanaṃ dātavyam iti kriyākāraṃ kṛtvāvasthitāḥ \| ⟦3 consecutive blank lines⟧ next: āyuṣmān api saṃgharakṣitaḥ śānteneryāpathena teṣāṃ sakāśam upa
  - line 494: 3 consecutive blank lines — previous: ād āyuṣmatā saṃgharakṣitena nagaropamaṃ sūtram upanikṣiptam \|\| ⟦3 consecutive blank lines⟧ next: pūrvaṃ me bhikṣavaḥ saṃbodhim anabhisaṃbuddhasyaikākino rahoga
  - line 516: 3 consecutive blank lines — previous: a vijñānāt pratyudāvartate mānasaṃ nātaḥ pareṇa vyativartate \| ⟦3 consecutive blank lines⟧ next: yad uta vijñānapratyayaṃ nāmarūpaṃ nāmarūpapratyayaṃ ṣaḍāyatan
- standalone_danda_line — 1 occurrence(s); source-specific separator / 不確定
  - line 723: \| — ⟦\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：multiple_blank_lines (10)、standalone_danda_line (1)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/vinv02_u.txt

**人工提示**

- 行首 |
- a b c d ... 類序號

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| line_start_single_danda | 53 | source-specific separator / 看起來像正文 boundary |
| enumeration_label | 43 | source-specific separator |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 70 |
| standalone_danda_line | 180 |
| line_start_single_danda | 53 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 14 |
| isolated_single_consonant | 29 |
| adjacent_vowels_non_ai_au | 0 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- enumeration_label — 43 occurrence(s); source-specific separator
  - line 335: a — ⟦a⟧ \| evaṃnāmā prahāṇapratijāgrako bhikṣur utsahate saṃghasya pra…
  - line 337: b — ⟦b⟧ \| tat saṃgha evaṃnāmānaṃ prahāṇapratijāgrakaṃ bhikṣuṃ saṃmany…
  - line 341: c — ⟦c⟧ \| yeṣām āyuṣmatāṃ kṣamate evaṃnāmānaṃ prahāṇapratijāgrakaṃ bh…
- isolated_single_consonant — 29 occurrence(s); apparatus / source-specific separator / 不確定
  - line 337: b — ⟦b⟧ \| tat saṃgha evaṃnāmānaṃ prahāṇapratijāgrakaṃ bhikṣuṃ saṃmany…
  - line 341: c — ⟦c⟧ \| yeṣām āyuṣmatāṃ kṣamate evaṃnāmānaṃ prahāṇapratijāgrakaṃ bh…
  - line 343: d — ⟦d⟧ \| saṃmataḥ saṃghena evaṃnāmā prahāṇapratijāgrako bhikṣuḥ \| ay…
- isolated_single_vowel — 14 occurrence(s); 不確定
  - line 335: a — ⟦a⟧ \| evaṃnāmā prahāṇapratijāgrako bhikṣur utsahate saṃghasya pra…
  - line 461: a — ⟦a⟧ \| idaṃ vastu sarvākārapariniṣṭhitam antaḥsīmaṃ bahirvyāmopavi…
  - line 577: a — ⟦a⟧ \| sminn āvāse āvāsikanaivāsikair bhikṣubhir mahatyāḥ sīmāyāś …
- line_start_single_danda — 53 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 21: \| — ⟦\|⟧ pratisaṃlīno bhagavān pratisaṃlīnāś ca manobhāvanīyāś ca bhik…
  - line 33: \| — ⟦\|⟧ ekāntaniṣaṇṇā rājagṛhīyakā upāsakā yāvān evaiṣām abhūt saṃbah…
  - line 43: \| — ⟦\|⟧ tasmād anujānāmi bhikṣubhir adyāgreṇa niṣadyā kriyā poṣadhaś …
- multiple_blank_lines — 70 occurrence(s); editorial / mechanical
  - line 1: 4 consecutive blank lines — previous:  ⟦4 consecutive blank lines⟧ next: \|\|
  - line 24: 3 consecutive blank lines — previous: \| ⟦3 consecutive blank lines⟧ next: \|
  - line 38: 3 consecutive blank lines — previous: \| ⟦3 consecutive blank lines⟧ next: \|
- standalone_danda_line — 180 occurrence(s); source-specific separator / 不確定
  - line 5: \|\| — ⟦\|\|⟧
  - line 11: \|\| — ⟦\|\|⟧
  - line 17: \| — ⟦\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (29)、isolated_single_vowel (14)、multiple_blank_lines (70)、standalone_danda_line (180)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/vinv03_u.txt

**人工提示**

- pravāv

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_pravav | 119 | source-specific separator |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 43 |
| standalone_danda_line | 5 |
| line_start_single_danda | 0 |
| line_start_double_danda | 6 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 0 |
| adjacent_vowels_non_ai_au | 0 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- line_start_double_danda — 6 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 55: \|\| — ⟦\|\|⟧ samanvāharāyuṣmann adya saṃghasya pravāraṇā pāñcadaśikā \| mam…
  - line 59: \|\| — ⟦\|\|⟧ pravāravakena pravārayitavyaṃ \|\|
  - line 65: \|\| — ⟦\|\|⟧ pravārayitavyaḥ tataḥ paścād bhikṣuṇyaḥ pravārayanti \|\|
- manual_pravav — 119 occurrence(s); source-specific separator
  - line 5: pravāv — ⟦pravāv⟧
  - line 9: pravāv — ⟦pravāv⟧
  - line 13: pravāv — ⟦pravāv⟧
- multiple_blank_lines — 43 occurrence(s); editorial / mechanical
  - line 1: 4 consecutive blank lines — previous:  ⟦4 consecutive blank lines⟧ next: pravāv
  - line 6: 3 consecutive blank lines — previous: pravāv ⟦3 consecutive blank lines⟧ next: pravāv
  - line 10: 3 consecutive blank lines — previous: pravāv ⟦3 consecutive blank lines⟧ next: pravāv
- standalone_danda_line — 5 occurrence(s); source-specific separator / 不確定
  - line 153: \| — ⟦\|⟧
  - line 247: \| — ⟦\|⟧
  - line 425: \| — ⟦\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：line_start_double_danda (6)、multiple_blank_lines (43)、standalone_danda_line (5)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/vinv04_u.txt

**人工提示**

- varv

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_varv | 101 | source-specific separator |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 4 |
| standalone_danda_line | 0 |
| line_start_single_danda | 1 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 11 |
| isolated_single_consonant | 14 |
| adjacent_vowels_non_ai_au | 0 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- isolated_single_consonant — 14 occurrence(s); apparatus / source-specific separator / 不確定
  - line 19: b — varv \| ⟦b⟧ pañcabhir dharmaiḥ samanvāgataḥ śayanāsanagrāhako bhikṣur asa…
  - line 53: b — varv \| ⟦b⟧ sacet saṃghasthaviro na gṛhṇāti dvitīyasthavirāya dātavyaḥ \| …
  - line 77: b — varv \| ⟦b⟧ kathaṃ gocaro 'valokayitavyaḥ \| kiṃ nu bhaviṣyanti me 'smiṃ g…
- isolated_single_vowel — 11 occurrence(s); 不確定
  - line 17: a — varv \| ⟦a⟧ pañcabhir dharmaiḥ samanvāgataḥ śayanāsanagrāhako bhikṣur asa…
  - line 51: a — varv \| ⟦a⟧ tataḥ paścāt śayanāsanagrāhakena bhikṣuṇā tāḍakaṃ kuṃcikāṃ ca…
  - line 85: a — varv \| ⟦a⟧ uktaṃ bhagavatā na bhikṣuṇā varṣoṣitena bahiḥsīmāṃ gantavyam …
- line_start_single_danda — 1 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 75: \| — ⟦\|⟧ glānasya vā glānopasthāyakaḥ \| evam āvāso 'valokayitavyaḥ \|
- manual_varv — 101 occurrence(s); source-specific separator
  - line 3: varv — ⟦varv⟧ \|\|
  - line 11: varv — ⟦varv⟧ \| uktaṃ bhagavatā bhikṣuṇā varṣā upagantavyam iti \| bhikṣavo …
  - line 13: varv — ⟦varv⟧ \| bhagavān āha \|\|
- multiple_blank_lines — 4 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: varv \|\|
  - line 4: 7 consecutive blank lines — previous: varv \|\| ⟦7 consecutive blank lines⟧ next: varv \| uktaṃ bhagavatā bhikṣuṇā varṣā upagantavyam iti \| bhikṣ
  - line 44: 3 consecutive blank lines — previous: varv \|\| ⟦3 consecutive blank lines⟧ next: varv \| tataḥ paścāt kriyākāra ārocayitavyaḥ \| śṛṇotu bhadantāḥ

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (14)、isolated_single_vowel (11)、line_start_single_danda (1)、multiple_blank_lines (4)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/vinv08_u.txt

**人工提示**

- kaṭhina v

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_kathina_v | 70 | source-specific separator |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 3 |
| isolated_single_consonant | 73 |
| adjacent_vowels_non_ai_au | 1 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 1 occurrence(s); 看起來像正文 / 不確定
  - line 211: ii — kaṭhina v ⟦ii⟧ \| yathā deśānuprekṣaṇapaṃcikā evam āvāsaprekṣaṇapaṃcikā \|\|
- isolated_single_consonant — 73 occurrence(s); apparatus / source-specific separator / 不確定
  - line 9: v — kaṭhina ⟦v⟧ buddho bhagavāṃ śrāvastyāṃ varṣā upagato jetavane 'nāthapiṇḍa…
  - line 11: v — kaṭhina ⟦v⟧ dharmatā khalu buddhā bhagavanta āgantukān bhikṣūn anayā prat…
  - line 13: v — kaṭhina ⟦v⟧ bhagavān saṃlakṣayati \| klāmyanti bata me śrāvakāḥ samādāya p…
- isolated_single_vowel — 3 occurrence(s); 不確定
  - line 25: a — kaṭhina v ⟦a⟧ \| śṛṇotu bhadantāḥ saṃgha ayam evaṃnāmā kaṭhināstārako bhikṣu…
  - line 53: a — kaṭhina v ⟦a⟧ \| śṛṇotu bhadantāḥ saṃgha yāvad evāsminn āvāse samagreṇa saṃg…
  - line 203: i — kaṭhina v ⟦i⟧ \| yathāpi tad bhikṣur āstīrṇakaṭhinād āvāsād akṛtacīvaro 'niṣ…
- manual_kathina_v — 70 occurrence(s); source-specific separator
  - line 9: kaṭhina v — ⟦kaṭhina v⟧ buddho bhagavāṃ śrāvastyāṃ varṣā upagato jetavane 'nāthapiṇḍa…
  - line 11: kaṭhina v — ⟦kaṭhina v⟧ dharmatā khalu buddhā bhagavanta āgantukān bhikṣūn anayā prat…
  - line 13: kaṭhina v — ⟦kaṭhina v⟧ bhagavān saṃlakṣayati \| klāmyanti bata me śrāvakāḥ samādāya p…

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (73)、isolated_single_vowel (3)。這些仍僅是候選，未作刪改判定。

## 4_rellit/buddh/vinv11_u.txt

**人工提示**

- pāṇḍ v |

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_pand_v | 95 | source-specific separator |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 1 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 1 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 193 |
| adjacent_vowels_non_ai_au | 3 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 3 occurrence(s); 看起來像正文 / 不確定
  - line 23: āi — pāṇḍ v \| paṃcabhiḥ kāraṇ⟦āi⟧s tarjanīyaṃ karma kṛtam adharmakarma ca tad avinayakarma ca s…
  - line 231: aā — …yatanasya ākiṃcanyāyatanasya naivasaṃjñānāsaṃjñāyatanasya srot⟦aā⟧pattiphalasya sakṛdāgāmiphalasya anāgāmiphalasya ṛddhiviṣayasy…
  - line 239: aā — …yatanasya ākiñcanyāyatanasya naivasaṃjñānāsaṃjñāyatanasya srot⟦aā⟧pattiphalasya sakṛdāgāmiphalasya anāgāmiphalasya riddhiviṣayas…
- isolated_single_consonant — 193 occurrence(s); apparatus / source-specific separator / 不確定
  - line 3: v — pāṇḍ ⟦v⟧ \|\| vastūddānam \|\|
  - line 5: ś — pāṇḍulohitakānāṃ vastū pudgalānāṃ tathaiva ca ⟦ś⟧
  - line 7: ś — atha pārivāsikānāṃ poṣadhasthāpanena ca ⟦ś⟧
- line_start_double_danda — 1 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 249: \|\| — ⟦\|\|⟧ pāṇḍulohitakavastu samāptaḥ \|\|
- manual_pand_v — 95 occurrence(s); source-specific separator
  - line 3: pāṇḍ v \| — ⟦pāṇḍ v \|⟧\| vastūddānam \|\|
  - line 11: pāṇḍ v \| — ⟦pāṇḍ v \|⟧\| paṇḍulohitakavastūddānam \|\|
  - line 21: pāṇḍ v \| — ⟦pāṇḍ v \|⟧ buddho bhagavāṃ śrāvastyāṃ viharati jetavane anāthapiṇḍadasyā…
- multiple_blank_lines — 1 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: pāṇḍ v \|\| vastūddānam \|\|

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (193)、line_start_double_danda (1)、multiple_blank_lines (1)。這些仍僅是候選，未作刪改判定。

## 4_rellit/vaisn/ss4_krsu.txt

**人工提示**

- 英文殘留

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| english_residue | 100 | editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 21 |
| standalone_danda_line | 16 |
| line_start_single_danda | 9 |
| line_start_double_danda | 111 |
| isolated_single_vowel | 13 |
| isolated_single_consonant | 11 |
| adjacent_vowels_non_ai_au | 210 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 210 occurrence(s); 看起來像正文 / 不確定
  - line 5: ea — edition app⟦ea⟧rs to be earlier than the vrindavan edition published by harid…
  - line 5: ea — edition appears to be ⟦ea⟧rlier than the vrindavan edition published by haridas
  - line 5: ie — edition appears to be earl⟦ie⟧r than the vrindavan edition published by haridas
- english_residue — 100 occurrence(s); editorial
  - line 5: appears — edition ⟦appears⟧ to be earlier than the vrindavan edition published by haridas
  - line 5: earlier — edition appears to be ⟦earlier⟧ than the vrindavan edition published by haridas
  - line 5: edition — ⟦edition⟧ appears to be earlier than the vrindavan edition published by…
- isolated_single_consonant — 11 occurrence(s); apparatus / source-specific separator / 不確定
  - line 13: s — thakur in the ⟦s⟧ \|
  - line 333: b — ⟦b⟧ \| reads here \| tatra śrībhagavantaṃ suṣṭhu spaṣṭīkartuṃ garbh…
  - line 1467: b — ⟦b⟧ reads here \| evam eva taṃ pratyuktaṃ devair apy ekādaśe \|\| ta…
- isolated_single_vowel — 13 occurrence(s); 不確定
  - line 17: o — dākṣiṇātyena bhaṭṭena punar etad vivicyate \|\| ⟦o⟧ \|\|
  - line 21: o — paryālocyātha paryāyaṃ kṛtvā likhati jīvakaḥ \|\| ⟦o⟧ \|\|
  - line 1675: u — prasiddhārthe nāyaṃ śriyo'ṅga ⟦u⟧ nitāntarateḥ prasādaḥ svaryoṣitāṃ nalina \|
- line_start_double_danda — 111 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 721: \|\| — ⟦\|\|⟧ śrīsūtaḥ \|\|
  - line 1353: \|\| — ⟦\|\|⟧ śrībhagavān \|\|
  - line 1369: \|\| — ⟦\|\|⟧ devāḥ śrībhagavantam \|\|
- line_start_single_danda — 9 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 665: \| — ⟦\|⟧ ete proktā avatārāḥ \| mūlarūpī svayam eva \| kiṃsvarūpā \| svāṃ…
  - line 2667: \| — ⟦\|⟧ devakīnandano nikhilam ānandayād iti ca \| tad ittham eva taṃ
  - line 3961: \| — ⟦\|⟧ nanu bālāturādy \|
- multiple_blank_lines — 21 occurrence(s); editorial / mechanical
  - line 2: 3 consecutive blank lines — previous: śrīkṛṣṇasandarbha ⟦3 consecutive blank lines⟧ next: edition appears to be earlier than the vrindavan edition publi
  - line 6: 7 consecutive blank lines — previous:  to be earlier than the vrindavan edition published by haridas ⟦7 consecutive blank lines⟧ next: thakur in the s \|
  - line 112: 3 consecutive blank lines — previous: pauruṣarūpasyāmbhasi pralayakālīnagarbhodake śayānasya sataḥ \| ⟦3 consecutive blank lines⟧ next: pūrṇaṣaḍaiśvaryatvena pūrvaṃ nirdiṣṭaḥ \| sa eva pauruṣaṃ rūpaṃ
- standalone_danda_line — 16 occurrence(s); source-specific separator / 不確定
  - line 59: \|\| — ⟦\|\|⟧
  - line 247: \| — ⟦\|⟧
  - line 805: \|\| — ⟦\|\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (11)、isolated_single_vowel (13)、line_start_double_danda (111)、line_start_single_danda (9)、multiple_blank_lines (21)、standalone_danda_line (16)。這些仍僅是候選，未作刪改判定。

## 5_poetry/2_kavya/amaru_u.txt

**人工提示**

- 英文說明
- abbreviation / correspondence table 範圍

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| english_residue | 13 | editorial |
| abbreviation_table_row | 12 | apparatus |

- abbreviation/correspondence table 實際為 lines 31–41 與 1105–1115（各 6 個 nonblank rows；第二段是重複 block）。

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 105 |
| standalone_danda_line | 13 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 0 |
| adjacent_vowels_non_ai_au | 13 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- abbreviation_table_row — 12 occurrence(s); apparatus
  - line 31: su \|\| subhāṣitaratnakoṣa \| — ⟦su \|\| subhāṣitaratnakoṣa \|⟧
  - line 33: sad \|\| saduktikarṇāmṛta \| — ⟦sad \|\| saduktikarṇāmṛta \|⟧
  - line 35: subh \|\| subhāṣitāvalī \| — ⟦subh \|\| subhāṣitāvalī \|⟧
- adjacent_vowels_non_ai_au — 13 occurrence(s); 看起來像正文 / 不確定
  - line 3: ia — abbrev⟦ia⟧tions
  - line 3: io — abbreviat⟦io⟧ns
  - line 5: io — this edit⟦io⟧n is based on the one in kāvyasaṅgraha edited by jīvānanda
- english_residue — 13 occurrence(s); editorial
  - line 3: abbreviations — ⟦abbreviations⟧
  - line 5: based — this edition is ⟦based⟧ on the one in kāvyasaṅgraha edited by jīvānanda
  - line 5: edited — this edition is based on the one in kāvyasaṅgraha ⟦edited⟧ by jīvānanda
- multiple_blank_lines — 105 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: abbreviations
  - line 6: 13 consecutive blank lines — previous: ition is based on the one in kāvyasaṅgraha edited by jīvānanda ⟦13 consecutive blank lines⟧ next: in that edition to be interpolations \| those suspect verses ha
  - line 20: 11 consecutive blank lines — previous: to be interpolations \| those suspect verses have been noted in ⟦11 consecutive blank lines⟧ next: su \|\| subhāṣitaratnakoṣa \|
- standalone_danda_line — 13 occurrence(s); source-specific separator / 不確定
  - line 117: \|\| — ⟦\|\|⟧
  - line 1579: \| — ⟦\|⟧
  - line 1589: \| — ⟦\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：multiple_blank_lines (105)、standalone_danda_line (13)。這些仍僅是候選，未作刪改判定。

## 5_poetry/2_kavya/nkalivpu.txt

**人工提示**

- 殘留校勘註釋

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| apparatus_residue | 3 | apparatus |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 2 |
| adjacent_vowels_non_ai_au | 1 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 1 occurrence(s); 看起來像正文 / 不確定
  - line 203: aṛ — uttam⟦aṛ⟧ṇāḥ
- apparatus_residue — 3 occurrence(s); apparatus
  - line 13: b \| udghoṣya \| ed \|\| udghuṣya — ⟦b \| udghoṣya \| ed \|\| udghuṣya⟧
  - line 51: em \| sukhe sukhiṣu — ⟦em \| sukhe sukhiṣu⟧
  - line 231: b \| em \|\| visaṃsthulau \| ed \|\| visaṃsphuṭau — ⟦b \| em \|\| visaṃsthulau \| ed \|\| visaṃsphuṭau⟧
- isolated_single_consonant — 2 occurrence(s); apparatus / source-specific separator / 不確定
  - line 13: b — ⟦b⟧ \| udghoṣya \| ed \|\| udghuṣya
  - line 231: b — ⟦b⟧ \| em \|\| visaṃsthulau \| ed \|\| visaṃsphuṭau

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (2)。這些仍僅是候選，未作刪改判定。

## 5_poetry/2_kavya/ramodtpu.txt

**人工提示**

- a b c ... 類序號

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| enumeration_label | 14 | source-specific separator |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 7 |
| isolated_single_consonant | 7 |
| adjacent_vowels_non_ai_au | 0 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- enumeration_label — 14 occurrence(s); source-specific separator
  - line 3: a — atha bālakāṇḍaḥ \|\| ⟦a⟧ \|\|
  - line 165: c — iti śrīrāmodante bālakāṇḍaḥ samāptaḥ \|\| ⟦c⟧ \|\|
  - line 167: a — atha ayodhyākāṇḍaḥ \|\| ⟦a⟧ \|\|
- isolated_single_consonant — 7 occurrence(s); apparatus / source-specific separator / 不確定
  - line 165: c — iti śrīrāmodante bālakāṇḍaḥ samāptaḥ \|\| ⟦c⟧ \|\|
  - line 249: c — iti śrīrāmodante ayodhyākāṇḍaḥ samāptaḥ \|\| ⟦c⟧ \|\|
  - line 365: c — iti śrīrāmodante āraṇyakāṇḍaḥ samāptaḥ \|\| ⟦c⟧ \|\|
- isolated_single_vowel — 7 occurrence(s); 不確定
  - line 3: a — atha bālakāṇḍaḥ \|\| ⟦a⟧ \|\|
  - line 167: a — atha ayodhyākāṇḍaḥ \|\| ⟦a⟧ \|\|
  - line 251: a — atha āraṇyakāṇḍaḥ \|\| ⟦a⟧ \|\|

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (7)、isolated_single_vowel (7)。這些仍僅是候選，未作刪改判定。

## 5_poetry/4_narr/brkas_pu.txt

**人工提示**

- 英文殘留

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| english_residue | 12 | editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 4 |
| standalone_danda_line | 7 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 3 |
| isolated_single_consonant | 5 |
| adjacent_vowels_non_ai_au | 28 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 28 occurrence(s); 看起來像正文 / 不確定
  - line 3: ea — input by andr⟦ea⟧s bigger
  - line 24: ee — it s⟦ee⟧med to make more sense \| it is also an uncorrected version \|
  - line 24: io — it seemed to make more sense \| it is also an uncorrected vers⟦io⟧n \|
- english_residue — 12 occurrence(s); editorial
  - line 3: input — ⟦input⟧ by andreas bigger
  - line 24: also — it seemed to make more sense \| it is ⟦also⟧ an uncorrected version \|
  - line 24: sense — it seemed to make more ⟦sense⟧ \| it is also an uncorrected version \|
- isolated_single_consonant — 5 occurrence(s); apparatus / source-specific separator / 不確定
  - line 600: ś — sakampavacano 'vocan \| nīcai \| ⟦ś⟧ cañcalabhīrukaḥ \|\|
  - line 5128: s — tena dhairyaprakarṣeṇa \| manaḥ ⟦s⟧ \| amdhṛtya cañcalam \|
  - line 5674: v — vayam eva ⟦v⟧ \| isaṃ pūrvaṃ \| pibāmaḥ kalpyatām iti \|\|
- isolated_single_vowel — 3 occurrence(s); 不確定
  - line 4942: ā — sa samāhṛtavān kāntāḥ \| kumārīr ⟦ā⟧ mahodadheḥ \|\|
  - line 14546: ā — ⟦ā⟧ mṛtyos tvatsamīpasthā \| nayāmi divasān iti \|\|
  - line 15578: u — sarvam apy ujjhati sphītaṃ \| kim ⟦u⟧ grantham anarthakam \|\|
- multiple_blank_lines — 4 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: input by andreas bigger
  - line 4: 3 consecutive blank lines — previous: input by andreas bigger ⟦3 consecutive blank lines⟧ next: \|\|
  - line 8: 16 consecutive blank lines — previous: \|\| ⟦16 consecutive blank lines⟧ next: it seemed to make more sense \| it is also an uncorrected versi
- standalone_danda_line — 7 occurrence(s); source-specific separator / 不確定
  - line 7: \|\| — ⟦\|\|⟧
  - line 2082: \|\| — ⟦\|\|⟧
  - line 5692: \|\| — ⟦\|\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (5)、isolated_single_vowel (3)、multiple_blank_lines (4)、standalone_danda_line (7)。這些仍僅是候選，未作刪改判定。

## 5_poetry/5_subhas/vidsrgpu.txt

**人工提示**

- 疑似縮略語表內容與範圍

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| abbreviation_table_row | 22 | apparatus |

- 疑似縮略語表實際為 lines 3–45（22 個 nonblank correspondence rows）；line 47 起轉入作品標題／正文。

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 122 |
| standalone_danda_line | 53 |
| line_start_single_danda | 0 |
| line_start_double_danda | 41 |
| isolated_single_vowel | 26 |
| isolated_single_consonant | 1 |
| adjacent_vowels_non_ai_au | 22 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- abbreviation_table_row — 22 occurrence(s); apparatus
  - line 3: a \| rā \|\| anargharāghava — ⟦a \| rā \|\| anargharāghava⟧
  - line 5: amaru \| amaruśatakaḥ — ⟦amaru \| amaruśatakaḥ⟧
  - line 7: u \| nī \|\| ujjvalanīlamaṇi — ⟦u \| nī \|\| ujjvalanīlamaṇi⟧
- adjacent_vowels_non_ai_au — 22 occurrence(s); 看起來像正文 / 不確定
  - line 255: aā — bhadraṃ candrakale śivaṃ suranadi śreyaḥ kapāl⟦aā⟧vale kalyāṇaṃ bhujagendravalli kuśalaṃ viśve śaṭāsaṃtate \|
  - line 777: ae — …kṣaḥsphuratkaustubhaṃ niryan nābhisarojakuḍmalakuṭīgambhīrasām⟦ae⟧dhvani \|
  - line 2973: oa — kalyāṇaṃ parikalpyatāṃ pikakule rohantu vāñcāptay⟦oa⟧ḥ haṃsānām udayo 'stu pūrṇaśaśinaḥ stād bhadram indīvare \|
- isolated_single_consonant — 1 occurrence(s); apparatus / source-specific separator / 不確定
  - line 8627: r — murāreḥ \| ⟦r⟧ etau \|\|
- isolated_single_vowel — 26 occurrence(s); 不確定
  - line 3: a — ⟦a⟧ \| rā \|\| anargharāghava
  - line 7: u — ⟦u⟧ \| nī \|\| ujjvalanīlamaṇi
  - line 9: u — ⟦u⟧ \| rā \| ca \|\| uttararāmacarita
- line_start_double_danda — 41 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 199: \|\| — ⟦\|\|⟧ iti lokeśvaravrajyā \|\|
  - line 665: \|\| — ⟦\|\|⟧ iti śivagaṇavrajyā \|\|
  - line 949: \|\| — ⟦\|\|⟧ iti sūryavrajyā \|\|
- multiple_blank_lines — 122 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: a \| rā \|\| anargharāghava
  - line 56: 3 consecutive blank lines — previous: asaś ca mahākavīnāṃ teṣāṃ samuccayam anargham ahaṃ vidhāsye \|\| ⟦3 consecutive blank lines⟧ next: sugatavrajyā
  - line 94: 3 consecutive blank lines — previous: ocita \| sragbhedā abhayapradānacaraṇapreṅkhannakhāgrāṃśavaḥ \|\| ⟦3 consecutive blank lines⟧ next: śīlāmbhaḥpariṣekaśītaladṛḍhadhyānālavālasphurad \| dānaskandham
- standalone_danda_line — 53 occurrence(s); source-specific separator / 不確定
  - line 149: \|\| — ⟦\|\|⟧
  - line 201: \|\| — ⟦\|\|⟧
  - line 233: \|\| — ⟦\|\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (1)、isolated_single_vowel (26)、line_start_double_danda (41)、multiple_blank_lines (122)、standalone_danda_line (53)。這些仍僅是候選，未作刪改判定。

## 6_sastra/3_phil/saiva/pratyabu.txt

**人工提示**

- 所有孤立 m

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_isolated_m | 8 | apparatus / source-specific separator / 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 9 |
| standalone_danda_line | 7 |
| line_start_single_danda | 2 |
| line_start_double_danda | 1 |
| isolated_single_vowel | 15 |
| isolated_single_consonant | 14 |
| adjacent_vowels_non_ai_au | 4 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 4 occurrence(s); 看起來像正文 / 不確定
  - line 1265: ia — netra t \| b \| la versione originale cui si rich⟦ia⟧ma kṣemarāja \|
  - line 1265: io — netra t \| b \| la vers⟦io⟧ne originale cui si richiama kṣemarāja \|
  - line 1265: ui — netra t \| b \| la versione originale c⟦ui⟧ si richiama kṣemarāja \|
- isolated_single_consonant — 14 occurrence(s); apparatus / source-specific separator / 不確定
  - line 21: m — ⟦m⟧
  - line 59: m — ⟦m⟧
  - line 115: y — ⟦y⟧
- isolated_single_vowel — 15 occurrence(s); 不確定
  - line 107: ā — ⟦ā⟧
  - line 329: a — ⟦a⟧
  - line 353: ā — ⟦ā⟧
- line_start_double_danda — 1 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 1145: \|\| — ⟦\|\|⟧ ta ete śivadharmiṇaḥ \| ityantaṃ śrīspande \|
- line_start_single_danda — 2 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 109: \| — ⟦\|⟧ evaṃ hi prāguktasvātantryahānyā cittvam eva na ghaṭeta \| svab…
  - line 309: \| — ⟦\|⟧ prakāśa eva yataḥ svātantryāt gṛhītaprāṇādisaṃkocaḥ
- manual_isolated_m — 8 occurrence(s); apparatus / source-specific separator / 不確定
  - line 21: m — ⟦m⟧
  - line 59: m — ⟦m⟧
  - line 137: m — ⟦m⟧
- multiple_blank_lines — 9 occurrence(s); editorial / mechanical
  - line 1240: 25 consecutive blank lines — previous: śubham astu ⟦25 consecutive blank lines⟧ next: netra t \| b \| la versione originale cui si richiama kṣemarāja
  - line 1266: 3 consecutive blank lines — previous: etra t \| b \| la versione originale cui si richiama kṣemarāja \| ⟦3 consecutive blank lines⟧ next: la seguente
  - line 1274: 5 consecutive blank lines — previous: ed \| apūrṇaṃ manyatārūpaṃ \| ⟦5 consecutive blank lines⟧ next: mss \| adyar library \| ed \|\| atyantaṃ
- standalone_danda_line — 7 occurrence(s); source-specific separator / 不確定
  - line 295: \|\| — ⟦\|\|⟧
  - line 357: \| — ⟦\|⟧
  - line 361: \| — ⟦\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (14)、isolated_single_vowel (15)、line_start_double_danda (1)、line_start_single_danda (2)、multiple_blank_lines (9)、standalone_danda_line (7)。這些仍僅是候選，未作刪改判定。

## 6_sastra/3_phil/samkhya/isvskaru.txt

**人工提示**

- 所有孤立單字母／單輔音

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| isolated_single_vowel | 9 | 不確定 |
| isolated_single_consonant | 116 | apparatus / source-specific separator / 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 41 |
| standalone_danda_line | 1 |
| line_start_single_danda | 3 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 9 |
| isolated_single_consonant | 116 |
| adjacent_vowels_non_ai_au | 4 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 4 occurrence(s); 看起來像正文 / 不確定
  - line 177: aṛa — sāmānyak⟦aṛa⟧ṇavṛttiḥ prāṇā \| dyā vāyavaḥ pañca \|
  - line 403: io — this verse is missing in paramārthas chinese vers⟦io⟧n
  - line 449: ii — gatam ⟦ii⟧śvarakṛṣṇena c aitad āryābhiḥ
- isolated_single_consonant — 116 occurrence(s); apparatus / source-specific separator / 不確定
  - line 3: n — dṛṣṭe sā pārthā cen ⟦n⟧ aikāntātyantato \| abhāvāt \|
  - line 5: g — abhi m \| ⟦g⟧ \| ava j \| s
  - line 5: j — abhi m \| g \| ava ⟦j⟧ \| s
- isolated_single_vowel — 9 occurrence(s); 不確定
  - line 475: a — ⟦a⟧
  - line 629: ā — ⟦ā⟧
  - line 631: ā — ⟦ā⟧
- line_start_single_danda — 3 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 79: \| — ⟦\|⟧ ādeḥ siddhis v \| d \| s \|\| ādir hi siddhaṃ k viparyaye v
  - line 301: \| — ⟦\|⟧ ramāt pañca ca y \| v \| k \|\| ramāt pañca j \| m \| b \| s \|
  - line 469: \| — ⟦\|⟧ ca m
- multiple_blank_lines — 41 occurrence(s); editorial / mechanical
  - line 28: 3 consecutive blank lines — previous: tal āptaśrutir āptavacanaṃ tu ⟦3 consecutive blank lines⟧ next: sāmānyatas tu dṛṣṭād atīndriyāṇām pratītir anumānāt
  - line 34: 3 consecutive blank lines — previous: tasmād api cā \| siddham paro \| akṣam āptā \| gamāt siddham ⟦3 consecutive blank lines⟧ next: atidūrāt sāmīpyād indriyaghātān mano \| anavasthānāt
  - line 70: 3 consecutive blank lines — previous: guru varaṇakam eva tamaḥ pradīpavac cā rthato vṛttiḥ \| ⟦3 consecutive blank lines⟧ next: avivekyādi hi siddhaṃ traiguṇyāt
- standalone_danda_line — 1 occurrence(s); source-specific separator / 不確定
  - line 905: \| — ⟦\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：line_start_single_danda (3)、multiple_blank_lines (41)、standalone_danda_line (1)。這些仍僅是候選，未作刪改判定。

## 6_sastra/4_dharma/sutra/apastd_u.txt

**人工提示**

- 疑似英文殘留

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| english_residue | 25 | editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 1313 |
| line_start_double_danda | 6 |
| isolated_single_vowel | 93 |
| isolated_single_consonant | 10 |
| adjacent_vowels_non_ai_au | 432 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 432 occurrence(s); 看起來像正文 / 不確定
  - line 1: aa — \| ath⟦aa⟧tas \| sāmayācārikān
  - line 16: aa — …tamaḥ praviśati pra \| viś yam avidvān upanayate upa \| nī yaś c⟦aa⟧vidvān iti hi brāhmanam \|
  - line 20: ae — \| tasmiṃś c⟦ae⟧va vidyā \| karma \| antam avipratipanne vi \| prati \| pad dharme…
- english_residue — 25 occurrence(s); editorial
  - line 18: opt — …t \| i samāhitam sam \| ā \| dhā saṃskartāram īpset \| āp \| des \| ⟦opt⟧ \|\|
  - line 24: opt — \| tasmai na druhyet \| druh \| ⟦opt⟧ \| kadā cana \|
  - line 26: caus — \| sa hi vidyātas taṃ janayati \| jan \| ⟦caus⟧ \|\|
- isolated_single_consonant — 10 occurrence(s); apparatus / source-specific separator / 不確定
  - line 468: k — …akty adhihastyam ādāya ā \| dā \| api danta \| prakṣālanāniiti \| ⟦k⟧ inserts mātaraṃ pitaram ācaryam agnīṃś ca gṛhāṇi ca rikta \| p…
  - line 1673: k — …ī vāg iti \|\| etāni vai sato \| agāre na kṣīyante kadācanaiti \| ⟦k⟧ om \|\|
  - line 1677: k — …hīyāanāyaāsanam udakam annam iti deyam \|\| na pratyuttiṣṭhet \| ⟦k⟧ om \|\|
- isolated_single_vowel — 93 occurrence(s); 不確定
  - line 18: i — \| tasminn abhijana \| vidyā \| samudetam sam \| ut \| ⟦i⟧ samāhitam sam \| ā \| dhā saṃskartāram īpset \| āp \| des \| opt \|…
  - line 18: ā — …inn abhijana \| vidyā \| samudetam sam \| ut \| i samāhitam sam \| ⟦ā⟧ \| dhā saṃskartāram īpset \| āp \| des \| opt \|\|
  - line 22: ā — \| yasmātdharmān ācinoti ⟦ā⟧ \| ci sa ācāryaḥ \|
- line_start_double_danda — 6 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 1168: \|\| — ⟦\|\|⟧ pūḥ prāṇinaḥ sarva eva guhā \| śayasya \| ahanyamānasya vikalma…
  - line 1174: \|\| — ⟦\|\|⟧ sarva \| bhūteṣu yo nityo vipaścid amṛto dhruvaḥ \| anaṅgo \| aś…
  - line 1179: \|\| — ⟦\|\|⟧ nipuṇo \| aṇīyān bisorṇāyā yaḥ sarvam āvṛtya tiṣṭhati \| varṣīy…
- line_start_single_danda — 1313 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 1: \| — ⟦\|⟧ athaatas \| sāmayācārikān
  - line 2: \| — ⟦\|⟧ dharmajña \| samayaḥ pramāṇam \| vedāś ca \|
  - line 4: \| — ⟦\|⟧ catvāro varṇo brāhmaṇa \| kṣatriya \| vaiśya \| śūdrāḥ \| teṣāṃ p…

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (10)、isolated_single_vowel (93)、line_start_double_danda (6)、line_start_single_danda (1313)。這些仍僅是候選，未作刪改判定。

## 6_sastra/4_dharma/sutra/vaikhd_u.txt

**人工提示**

- vaikh |

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| manual_vaikh | 343 | source-specific separator |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 1 |
| standalone_danda_line | 0 |
| line_start_single_danda | 1 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 18 |
| isolated_single_consonant | 1 |
| adjacent_vowels_non_ai_au | 262 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 262 occurrence(s); 看起來像正文 / 不確定
  - line 11: aa — vaikh \| tasmād brāhmaṇasy⟦aa⟧dhyayana \| adhyāpana \| yajana \| yājana \| dāna \| pratigrahāṇi ṣ…
  - line 19: ae — vaikh \| śūdrasya dvijamanāṃ śuśrūṣā kṛṣiś c⟦ae⟧va \|
  - line 21: aā — vaikh \| brāhmaṇasy⟦aā⟧śramāś catvāraḥ kṣatriyasyaādyās trayo vaiśyasya dvāv eva \|
- english_residue — 2 occurrence(s); editorial
  - line 549: cal read — vaikh \| kauśeya \| āvikāny ūṣair aṃśutaṭṭāni \| ⟦cal read⟧saṃśupaṭṭa \| in his tr \| p \| śrīphalaiḥ śaṅkha \| śukti \| gośṛ…
  - line 549: in his tr — …kauśeya \| āvikāny ūṣair aṃśutaṭṭāni \| cal readsaṃśupaṭṭa \| ⟦in his tr⟧ \| p \| śrīphalaiḥ śaṅkha \| śukti \| gośṛṅgāṇi sarṣapaiḥ…
- isolated_single_consonant — 1 occurrence(s); apparatus / source-specific separator / 不確定
  - line 549: p — … āvikāny ūṣair aṃśutaṭṭāni \| cal readsaṃśupaṭṭa \| in his tr \| ⟦p⟧ \| śrīphalaiḥ śaṅkha \| śukti \| gośṛṅgāṇi sarṣapaiḥ sa \| vāribh…
- isolated_single_vowel — 18 occurrence(s); 不確定
  - line 55: a — … śikhī vā mekhalī daṇḍī sūtra \| ajina \| dhārībrahmacārī śucir ⟦a⟧ \| kṣāra \| lavaṇa \| āśī yāvad ātmano viprayogas tāvad guru \| k…
  - line 107: a — vaikh \| ⟦a⟧ \| patnīkā bahuvidhāḥ \|
  - line 121: ā — vaikh paramahaṃsā nāma vṛkṣa \| ekamūle śūnya \| agāreśmaśāne ⟦ā⟧ vāsinaḥ sa \| ambarā dig \| ambarā vā \|
- line_start_single_danda — 1 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 659: \| — ⟦\|⟧ karoti \|
- manual_vaikh — 343 occurrence(s); source-specific separator
  - line 1: vaikh \| — ⟦vaikh \|⟧ atha varṇa \| āśrama \| dharmaṃ
  - line 3: vaikh \| — ⟦vaikh \|⟧ brāhmaṇa \| kṣatriya \| vaiśya \| śūdrāmukha \| bāhu \| ūru \| pāde…
  - line 5: vaikh \| — ⟦vaikh \|⟧ yasmād brāhmaṇo asya mukham \| āsīd iti śrutiḥ \|
- multiple_blank_lines — 1 occurrence(s); editorial / mechanical
  - line 314: 3 consecutive blank lines — previous: tathā bhikṣā \| pātram alābu dāravaṃ mṛn \| mayaṃ vā \| gṛhṇāti \| ⟦3 consecutive blank lines⟧ next: vaikh \| ud vayaṃ tamasa ity ādityam \| upatiṣṭheta \|

**同文件中的同類／相關可疑項**

- 有；另見：english_residue (2)、isolated_single_consonant (1)、isolated_single_vowel (18)、line_start_single_danda (1)、multiple_blank_lines (1)。其中 line 549 的兩個 English spans 看起來像 editorial/apparatus，其餘仍僅是候選；未作刪改判定。

## 6_sastra/4_dharma/sutra/vasist_u.txt

**人工提示**

- a | 等異常短片段

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| short_danda_fragment_candidate | 372 | 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 1 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 115 |
| isolated_single_consonant | 0 |
| adjacent_vowels_non_ai_au | 0 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- isolated_single_vowel — 115 occurrence(s); 不確定
  - line 13: a — ⟦a⟧ \| gṛhyamāṇa \| kāraṇas dharmas \|\|
  - line 61: a — atas hi dhruvas kula \| apakarṣas pretya ca ⟦a⟧ \| svargas \|\|
  - line 119: a — …tena iha asya aurasī prajā jāyate \| tasmāt śrotriyam anūcānam ⟦a⟧ \| prajas asi iti
- line_start_single_danda — 1 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 565: \| — ⟦\|⟧ sas abravīt varam vṛṇīdhvam iti \| tās abruvan ṛtau prajām vin…
- short_danda_fragment_candidate — 372 occurrence(s); 不確定
  - line 9: tad — ⟦tad⟧ \| alābhe śiṣṭa \| ācāras pramāṇam \|\|
  - line 11: ātmā — śiṣṭas punar akāma \| ⟦ātmā⟧ \|\|
  - line 13: a — ⟦a⟧ \| gṛhyamāṇa \| kāraṇas dharmas \|\|

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_vowel (115)、line_start_single_danda (1)。這些仍僅是候選，未作刪改判定。

## 6_sastra/5_artha/kautil_u.txt

**人工提示**

- 英文殘留
- 行中 single |、句末 |、||

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| english_residue | 4 | editorial |
| internal_single_danda | 20775 | 看起來像正文 boundary / 不確定 |
| line_end_single_danda | 392 | 看起來像正文 boundary / 不確定 |
| double_danda | 5454 | 看起來像正文 boundary / 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 151 |
| standalone_danda_line | 4 |
| line_start_single_danda | 24 |
| line_start_double_danda | 1 |
| isolated_single_vowel | 202 |
| isolated_single_consonant | 83 |
| adjacent_vowels_non_ai_au | 24 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 24 occurrence(s); 看起來像正文 / 不確定
  - line 5: io — prose sect⟦io⟧ns are subdivided by a \| b \| c \| etc \|\|
  - line 81: aa — śāstra \| samuddeśaḥ pañcadaśa \| adhikaraṇāni s⟦aa⟧śīti \| prakaraṇa \| śataṃ sapañcāśad \| adhyāya \| śataṃ ṣaṭ \| śl…
  - line 365: aa — purohitam udita \| udita \| kula \| śīlaṃ s⟦aa⟧ṅge vede daive nimitte daṇḍa \| nītyāṃ ca abhivinītam āpadāṃ da…
- double_danda — 5454 occurrence(s); 看起來像正文 boundary / 不確定
  - line 5: \|\| — prose sections are subdivided by a \| b \| c \| etc ⟦\|\|⟧
  - line 13: \|\| — oṃ \| namaḥ \| śukra \| bṛhaspatibhyāṃ ⟦\|\|⟧
  - line 15: \|\| — …pitāni prāyaśas tāni saṃhṛtya ekam idam artha \| śāstraṃ kṛtam ⟦\|\|⟧
- english_residue — 4 occurrence(s); editorial
  - line 5: etc — prose sections are subdivided by a \| b \| c \| ⟦etc⟧ \|\|
  - line 5: prose — ⟦prose⟧ sections are subdivided by a \| b \| c \| etc \|\|
  - line 5: sections — prose ⟦sections⟧ are subdivided by a \| b \| c \| etc \|\|
- internal_single_danda — 20775 occurrence(s); 看起來像正文 boundary / 不確定
  - line 5: \| — prose sections are subdivided by a ⟦\|⟧ b \| c \| etc \|\|
  - line 5: \| — prose sections are subdivided by a \| b ⟦\|⟧ c \| etc \|\|
  - line 5: \| — prose sections are subdivided by a \| b \| c ⟦\|⟧ etc \|\|
- isolated_single_consonant — 83 occurrence(s); apparatus / source-specific separator / 不確定
  - line 5: b — prose sections are subdivided by a \| ⟦b⟧ \| c \| etc \|\|
  - line 5: c — prose sections are subdivided by a \| b \| ⟦c⟧ \| etc \|\|
  - line 1051: ś — sarvam ātyayikaṃ kāryaṃ śṛṇuyān na atipātayet \| ⟦ś⟧
- isolated_single_vowel — 202 occurrence(s); 不確定
  - line 5: a — prose sections are subdivided by ⟦a⟧ \| b \| c \| etc \|\|
  - line 85: e — kauṭilyena kṛtaṃ śāstraṃ vimukta \| grantha \| vistaram \|\| ⟦e⟧
  - line 115: e — āśrayaḥ sarva \| dharmāṇāṃ śaśvad ānvīkṣikī matā \|\| ⟦e⟧
- line_end_single_danda — 392 occurrence(s); 看起來像正文 boundary / 不確定
  - line 7: \| — \| kauṭilīya \| artha \| śāstraṃ ⟦\|⟧
  - line 27: \| — …rma \| anta \| pravartanam \| akṣa \| śālāyāṃ suvarṇa \| adhyakṣaḥ ⟦\|⟧
  - line 43: \| — …ṣā \| vākya \| karma \| anuyogaḥ \| sarva \| adhikaraṇa \| rakṣaṇaṃ ⟦\|⟧
- line_start_double_danda — 1 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 1529: \|\| — ⟦\|\|⟧ bāhyam abhyantaraṃ cāyaṃ vidyād varṣa \| śatād api \| ś
- line_start_single_danda — 24 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 7: \| — ⟦\|⟧ kauṭilīya \| artha \| śāstraṃ \|
  - line 15: \| — ⟦\|⟧ pṛthivyā lābhe pālane ca yāvanty artha \| śāstrāṇi pūrva \| ācā…
  - line 1083: \| — ⟦\|⟧ kośagṛha \| vidhānena madhye vāsa \| gṛham \| gūḍha \| bhitti \| s…
- multiple_blank_lines — 151 occurrence(s); editorial / mechanical
  - line 1: 4 consecutive blank lines — previous:  ⟦4 consecutive blank lines⟧ next: prose sections are subdivided by a \| b \| c \| etc \|\|
  - line 8: 5 consecutive blank lines — previous: \| kauṭilīya \| artha \| śāstraṃ \| ⟦5 consecutive blank lines⟧ next: oṃ \| namaḥ \| śukra \| bṛhaspatibhyāṃ \|\|
  - line 86: 5 consecutive blank lines — previous: kauṭilyena kṛtaṃ śāstraṃ vimukta \| grantha \| vistaram \|\| e ⟦5 consecutive blank lines⟧ next: ānvīkṣikī trayī vārttā daṇḍa \| nītiś ca iti vidyāḥ \|\|
- standalone_danda_line — 4 occurrence(s); source-specific separator / 不確定
  - line 6855: \|\| — ⟦\|\|⟧
  - line 8361: \|\| — ⟦\|\|⟧
  - line 8735: \|\| — ⟦\|\|⟧

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (83)、isolated_single_vowel (202)、line_start_double_danda (1)、line_start_single_danda (24)、multiple_blank_lines (151)、standalone_danda_line (4)。這些仍僅是候選，未作刪改判定。

## 6_sastra/8_jyot/aryabh_u.txt

**人工提示**

- 異常短 token／單音節片段

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| short_danda_fragment_candidate | 54 | 不確定 |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 8 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 0 |
| adjacent_vowels_non_ai_au | 109 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 109 occurrence(s); 看起來像正文 / 不確定
  - line 7: aa — varg⟦aa⟧kṣarāṇi varge avarge avargaakṣarāṇi kāt \| ṅmau \| yas \|
  - line 7: aa — vargaakṣarāṇi varge avarge avarg⟦aa⟧kṣarāṇi kāt \| ṅmau \| yas \|
  - line 17: aa — \| buphinaca pātavilomās budh⟦aa⟧hni ajaarkaudayāt ca laṅkāyām \|\|
- line_start_single_danda — 8 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 9: \| — ⟦\|⟧ kha \| dvi \| navake svarās nava varge avarge nava antyavarge v…
  - line 17: \| — ⟦\|⟧ buphinaca pātavilomās budhaahni ajaarkaudayāt ca laṅkāyām \|\|
  - line 31: \| — ⟦\|⟧ bhaapakramas grahaaṃśās śaśivikṣepas apamaṇḍalāt \| jha \| ardh…
- short_danda_fragment_candidate — 54 occurrence(s); 不確定
  - line 7: yas — vargaakṣarāṇi varge avarge avargaakṣarāṇi kāt \| ṅmau \| ⟦yas⟧ \|
  - line 7: ṅmau — vargaakṣarāṇi varge avarge avargaakṣarāṇi kāt \| ⟦ṅmau⟧ \| yas \|
  - line 9: dvi — \| kha \| ⟦dvi⟧ \| navake svarās nava varge avarge nava antyavarge vā \|\|

**同文件中的同類／相關可疑項**

- 有；另見：line_start_single_danda (8)。這些仍僅是候選，未作刪改判定。

## 6_sastra/8_jyot/brhajj_u.txt

**人工提示**

- 有效 Sanskrit text 比例與成因

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| brhajj_residual_content | 28 | editorial / 不確定 |

- final：1404 chars、28 nonblank lines；IAST/apostrophe textual chars / nonspace chars = 394/444 (88.74%)。這是字元合規率，不代表語義正文率。
- 實際內容分布：24 個章名／目錄式 fragments、3 個 body-like 但不完整的 Sanskrit fragments、1 個 artificial repeated-a line；body-like lines = 3/28 (10.71%)。
- pre-strict checkpoint：5388 chars、434 nonblank lines；final/checkpoint character ratio = 26.06%。checkpoint 主要是目錄、metre labels 與極少殘句。
- raw HTML：94350 chars；找到 844 個 BJ_... body records（合計 83597 chars），raw line 133 起已有 BJ_01.01a/... 正文。
- final textual chars / raw BJ body-record chars = 394/83597 (0.47%)；此為量級比較，不把 HTML record 與 canonical line 當成一一對應。
- 判斷：不是來源文件本身幾乎無正文；正文存在於 raw HTML，但在進入 pre-strict checkpoint 前已幾乎未被保留。strict projection 再移除 checkpoint 中的數字、括號與 metre labels，只留下目錄詞和 aaaaaaaaaaaaaaaaa。問題主要在 upstream extraction/cleaning path，不是 whitelist。

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 7 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 0 |
| adjacent_vowels_non_ai_au | 1 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 1 occurrence(s); 看起來像正文 / 不確定
  - line 67: aaaaaaaaaaaaaaaaa — ⟦aaaaaaaaaaaaaaaaa⟧
- brhajj_residual_content — 28 occurrence(s); editorial / 不確定
  - line 3: rāśi \| prabheda — ⟦rāśi \| prabheda⟧
  - line 5: niṣeka — ⟦niṣeka⟧
  - line 7: ariṣṭa — ⟦ariṣṭa⟧
- multiple_blank_lines — 7 occurrence(s); editorial / mechanical
  - line 1: 2 consecutive blank lines — previous:  ⟦2 consecutive blank lines⟧ next: rāśi \| prabheda
  - line 48: 19 consecutive blank lines — previous: upasaṃhāra ⟦19 consecutive blank lines⟧ next: aaaaaaaaaaaaaaaaa
  - line 68: 63 consecutive blank lines — previous: aaaaaaaaaaaaaaaaa ⟦63 consecutive blank lines⟧ next: viyoni \| janma

**同文件中的同類／相關可疑項**

- 有；另見：multiple_blank_lines (7)。這些仍僅是候選，未作刪改判定。

## 6_sastra/8_jyot/brhats_u.txt

**人工提示**

- 英文殘留

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| english_residue | 8 | editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 7 |
| standalone_danda_line | 0 |
| line_start_single_danda | 48 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 96 |
| isolated_single_consonant | 1109 |
| adjacent_vowels_non_ai_au | 6 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 6 occurrence(s); 看起來像正文 / 不確定
  - line 17: ou — comp⟦ou⟧nds
  - line 2773: aā — bhavati bhayaṃ diśi tasyām āyudha kopa kṣudh⟦aā⟧ ātaṅkaiḥ \|\|
  - line 4751: aū — kiñ cid adh⟦aū⟧rdhva nirmitam k \| nirnatam upari viśālaṃ trayodaśaṃ ketoḥ \|
- english_residue — 8 occurrence(s); editorial
  - line 15: consonantal — ⟦consonantal⟧ sandhis are retained \|
  - line 15: retained — consonantal sandhis are ⟦retained⟧ \|
  - line 15: sandhis — consonantal ⟦sandhis⟧ are retained \|
- isolated_single_consonant — 1109 occurrence(s); apparatus / source-specific separator / 不確定
  - line 43: k — kuja dinam aniṣṭam iti vā ko atra viśeṣo nṛ divya kṛteḥ ⟦k⟧ \| kṛte \|\|
  - line 81: k — …ṣmān gambhīra udātta ghoṣaḥ \| prāyaḥ śarīra ākāra anuvarttino ⟦k⟧ \| anuvartino hi guṇā doṣāś ca bhavanti \|
  - line 83: k — tatra guṇāḥ \|\| śucir dakṣaḥ pragalbho vāggmī ⟦k⟧ \| vāgmī pratibhānavān deśa kāla vit sāttviko na parṣad bhīruḥ…
- isolated_single_vowel — 96 occurrence(s); 不確定
  - line 85: u — …ṣu yuga varṣa ayana ṛtu māsa pakṣa ahorātra yāma muhūrta nāḍī ⟦u⟧ \| nāḍī vināḍī prāṇa truṭi truṭy ādy avayava ādikasya k \| ādya…
  - line 145: ū — …mbala khaḍga paṭṭa kṛkavāku kūrma go aja aśva ibha purūṣa k \| ⟦ū⟧ \| puruṣa strī lakṣaṇāny
  - line 303: ū — dvaśyante k \|\| ⟦ū⟧ \| dṛśyante ca yatas te ravi bimbasya utthitā mahā utpātāḥ \|
- line_start_single_danda — 48 occurrence(s); source-specific separator / 看起來像正文 boundary
  - line 197: \| — ⟦\|⟧ nakṣatra sūcaka uddiṣṭam upahāsaṃ karoti yaḥ \|
  - line 199: \| — ⟦\|⟧ sa vrajaty andhatā misraṃ sārdham ṛkṣaviḍambinā \|\|
  - line 2323: \| — ⟦\|⟧ nāsikyabhogavardhanavirāṭavindhyādripārśvagā deśāḥ \|
- multiple_blank_lines — 7 occurrence(s); editorial / mechanical
  - line 1: 8 consecutive blank lines — previous:  ⟦8 consecutive blank lines⟧ next: ca iti ceti
  - line 18: 3 consecutive blank lines — previous: compounds ⟦3 consecutive blank lines⟧ next: but not consistent \|
  - line 24: 3 consecutive blank lines — previous: others ⟦3 consecutive blank lines⟧ next: upanayanādhyāyaḥ

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (1109)、isolated_single_vowel (96)、line_start_single_danda (48)、multiple_blank_lines (7)。這些仍僅是候選，未作刪改判定。

## 6_sastra/8_jyot/bijaganu.txt

**人工提示**

- 英文殘留

**Occurrence count（人工提示對應類別）**

| issue_type | count | 初步性質 |
|---|---:|---|
| english_residue | 2 | editorial |

**統一附帶檢查 count**

| issue_type | count |
|---|---:|
| leading_space | 0 |
| trailing_space | 0 |
| multiple_spaces | 0 |
| multiple_blank_lines | 0 |
| standalone_danda_line | 0 |
| line_start_single_danda | 0 |
| line_start_double_danda | 0 |
| isolated_single_vowel | 0 |
| isolated_single_consonant | 4 |
| adjacent_vowels_non_ai_au | 177 |
| apostrophe_abnormal_context | 0 |

**代表性上下文**

- adjacent_vowels_non_ai_au — 177 occurrence(s); 看起來像正文 / 不確定
  - line 1: aṛ — dhan⟦aṛ⟧ṇaṣaṣvidham
  - line 11: aṛ — yoge yutis syāt kṣayayos svayos vā dhan⟦aṛ⟧ṇayos antaram eva yogas \|
  - line 15: aṛ — sv⟦aṛ⟧ṇam kṣayam svam ca pṛthakpṛthaktve dhanaṛṇayos sṃkalanām avaiṣ…
- english_residue — 2 occurrence(s); editorial
  - line 17: prose — … lekhyāni \| tathā yāni ūnagatāni tāni ūrdhvabindūni ca iti \|\| ⟦prose⟧
  - line 19: prose — evam bhinneṣu api iti \|\| ⟦prose⟧
- isolated_single_consonant — 4 occurrence(s); apparatus / source-specific separator / 不確定
  - line 113: c — …amityos tribhasaṃkhyayos ca yogaantare brūhi sakhe karaṇyos \| ⟦c⟧ \| trisaptamityos ca ciram vicintya ced ṣaṣvidham vetsi sakhe …
  - line 119: c — … bhavet ca kṣayarūpavargas ced sādhyate asau karaṇītvahetos \| ⟦c⟧ \| ṛṇaātnikāyās ca tathā karaṇyās mūlam kṣayas rūpavidhānaheto…
  - line 125: g — …ayā bhājyagatās karaṇyas labdhās karaṇyas yadi yogajās syus \| ⟦g⟧ \| viśleṣasūtreṇa pṛthak ca kāryā yathā tathā praṣṭus abhīpsit…

**同文件中的同類／相關可疑項**

- 有；另見：isolated_single_consonant (4)。這些仍僅是候選，未作刪改判定。

## Integrity

- canonical path-and-content SHA-256 before report write: 8dd18b6f361d883d7ea629a483a9ea909aa469d3fe2132edc0e928bce9a24c5b
- canonical path-and-content SHA-256 after audit generation: 8dd18b6f361d883d7ea629a483a9ea909aa469d3fe2132edc0e928bce9a24c5b
- unchanged: true
- audit generator only read canonical/raw/checkpoint; its only output targets were this md and the companion tsv.
