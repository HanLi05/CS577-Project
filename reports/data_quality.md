# Pilot data quality

- Parsed transcripts: 87; parsed Q&A segments: 790.
- Accepted examples: 50 across 3 events.
- Match review was performed by the implementing AI agent, not a human annotator.
- Forward-looking rules are exploratory. Human annotation is pending; no precision/recall claim is made.
- Date-only transcript metadata supports a retrospective end-of-day cutoff, not a verified live publication time.
- Raw snapshots and transcript-derived outputs are local and ignored by Git. No redistribution rights are asserted.

## Exclusions and review queue

```
status         reason                                   
accepted       matched                                      50
excluded       ineligible_round                             16
               parse:multiple_speakers:SCOTTIE SCHEFFLER     1
review_needed  unmapped_player                               1
               unverified_timing                            20
```

## Full-field reconciliation

```
 event_id  round  expected_players  valid_players missing_players extra_players  verified   reason
401580329      1                59             59                                    True verified
401580329      2                59             59                                    True verified
401580329      3                59             59                                    True verified
401580329      4                59             59                                    True verified
401580330      1               144            144                                    True verified
401580330      2               144            144                                    True verified
401580330      3                82             82                                    True verified
401580330      4                81             81                                    True verified
401580334      1               132            132                                    True verified
401580334      2               131            131                                    True verified
401580334      3                73             73                                    True verified
401580334      4                73             73                                    True verified
401580335      1                70             70                                    True verified
401580335      2                69             69                                    True verified
401580335      3                51             51                                    True verified
401580335      4                51             51                                    True verified
401580336      1               132            132                                    True verified
401580336      2               128            128                                    True verified
401580336      3                65             65                                    True verified
401580336      4                65             65                                    True verified
401580339      1               132            132                                    True verified
401580339      2               132            132                                    True verified
401580339      3                72             72                                    True verified
401580339      4                72             72                                    True verified
401580340      1               143            143                                    True verified
401580340      2               142            142                                    True verified
401580340      3                73             73                                    True verified
401580340      4                73             73                                    True verified
401580341      1               152            152                                    True verified
401580341      2               147            147                                    True verified
401580341      3                77             77                                    True verified
401580341      4                77             77                                    True verified
401580342      1               144            144                                    True verified
401580342      2               143            143                                    True verified
401580342      3                83             83                                    True verified
401580342      4                83             83                                    True verified
401580343      1               156            156                                    True verified
401580343      2               153            153                                    True verified
401580343      3                82             82                                    True verified
401580343      4                82             82                                    True verified
401580344      1                89             89                                    True verified
401580344      2                89             89                                    True verified
401580344      3                60             60                                    True verified
401580344      4                60             60                                    True verified
401580345      1                69             69                                    True verified
401580345      2                69             69                                    True verified
401580345      3                69             69                                    True verified
401580345      4                69             69                                    True verified
401580346      1               132            132                                    True verified
401580346      2               132            132                                    True verified
401580346      3                70             70                                    True verified
401580346      4                70             70                                    True verified
401580348      1               154            154                                    True verified
401580348      2               153            153                                    True verified
401580348      3                66             66                                    True verified
401580348      4                66             66                                    True verified
401580349      1                68             68                                    True verified
401580349      2                68             68                                    True verified
401580349      3                68             68                                    True verified
401580349      4                68             68                                    True verified
401580350      1               132            132                                    True verified
401580350      2               132            132                                    True verified
401580350      3                70             70                                    True verified
401580350      4                70             70                                    True verified
401580351      1               156            156                                    True verified
401580351      2               153            153                                    True verified
401580351      3                78             78                                    True verified
401580351      4                78             78                                    True verified
401580352      1               132            132                                    True verified
401580352      2               129            129                                    True verified
401580352      3                71             71                                    True verified
401580352      4                71             71                                    True verified
401580353      1               156            156                                    True verified
401580353      2               154            154                                    True verified
401580353      3                69             69                                    True verified
401580353      4                69             69                                    True verified
401580354      1                73             73                                    True verified
401580354      2                73             73                                    True verified
401580354      3                52             52                                    True verified
401580354      4                52             52                                    True verified
401580355      1               156            156                                    True verified
401580355      2               156            156                                    True verified
401580355      3                74             74                                    True verified
401580355      4                74             74                                    True verified
401580356      1                70             70                                    True verified
401580356      2                70             70                                    True verified
401580356      3                70             70                                    True verified
401580356      4                70             70                                    True verified
401580357      1               156            156                                    True verified
401580357      2               154            154                                    True verified
401580357      3                74             74                                    True verified
401580357      4                74             74                                    True verified
401580358      1               156            156                                    True verified
401580358      2               155            155                                    True verified
401580358      3                77             77                                    True verified
401580358      4                77             77                                    True verified
401580359      1               156            156                                    True verified
401580359      2               153            153                                    True verified
401580359      3                74             74                                    True verified
401580359      4                74             74                                    True verified
401580362      1               156            156                                    True verified
401580362      2               155            155                                    True verified
401580362      3                75             75                                    True verified
401580362      4                74             74                                    True verified
401580363      1               156            156                                    True verified
401580363      2               153            153                                    True verified
401580363      3                67             67                                    True verified
401580363      4                66             66                                    True verified
401580364      1                70             70                                    True verified
401580364      2                70             70                                    True verified
401580364      3                70             70                                    True verified
401580364      4                70             70                                    True verified
401580365      1                50             50                                    True verified
401580365      2                49             49                                    True verified
401580365      3                48             48                                    True verified
401580365      4                48             48                                    True verified
401634279      1               156            156                                    True verified
401634279      2               154            154                                    True verified
401634279      3                67             67                                    True verified
401634279      4                67             67                                    True verified
401693936      1               144            144                                    True verified
401693936      2               142            142                                    True verified
401693936      3                65             65                                    True verified
401693936      4                65             65                                    True verified
401693937      1               131            131                                    True verified
401693937      2               128            128                                    True verified
401693937      3                68             68                                    True verified
401693937      4                68             68                                    True verified
401693938      1               131            131                                    True verified
401693938      2               127            127                                    True verified
401693938      3                69             69                                    True verified
401693938      4                69             69                                    True verified
401693939      1               132            132                                    True verified
401693939      2               130            130                                    True verified
401693939      3                66             66                                    True verified
401693939      4                66             66                                    True verified
401693940      1                78             78                                    True verified
401693940      2                77             77                                    True verified
401693940      3                77             77                                    True verified
401693940      4                77             77                                    True verified
401693941      1               120            120                                    True verified
401693941      2               120            120                                    True verified
401693941      3                68             68                                    True verified
401693941      4                67             67                                    True verified
401693942      1               120            120                                    True verified
401693942      2               115            115                                    True verified
401693942      3                75             75                                    True verified
401693942      4                75             75                                    True verified
```

Field means use all validated complete rounds, including players later cut or withdrawn. An event-round with a missing or mismatched complete player-round is quarantined.

## Dataset composition

```
event_id   round
401580340  3        12
401580352  1         5
           2         6
           3         3
401580354  1        10
           2         9
           3         5
```

Class counts: {0: 42, 1: 8}.
Unique interviewed players: 32; largest player share: 10.0%.
Empty forward-looking subsets: 1.
Answer character lengths (min/median/max): 553 / 3035 / 13399.

Missing feature counts:
```
current_strokes             0
current_relative_score      0
tournament_mean_relative    0
tournament_strokes          0
completed_rounds            0
history_5_mean              1
history_5_count             0
history_5_missing           0
history_20_mean             1
history_20_count            0
history_20_missing          0
```

## Selection bias and limits

Interviews are not a random sample of the field. Compare the following current-round averages descriptively; this is not an estimate of causal selection effects.

- THE PLAYERS Championship: interviewed mean relative score -3.454; all-player mean over represented rounds -0.000; 12/73 observed round-interviews.
- Charles Schwab Challenge: interviewed mean relative score -4.361; all-player mean over represented rounds -0.000; 14/332 observed round-interviews.
- the Memorial Tournament pres. by Workday: interviewed mean relative score -3.367; all-player mean over represented rounds 0.000; 24/198 observed round-interviews.

Only three pilot event groups are available. Splits exercise the machinery and cannot approximate 80/10/10 closely or support reliable model comparisons.
Historical features use validated single-course, ordinary individual stroke-play events available in the collected season. History before the season boundary is missing, not zero.
Random grouped splits are retrospective. The separate chronological manifest is the appropriate starting point for a forecasting robustness analysis.
This preparation report does not evaluate models. The separate optional statistics-only experiment writes results to `reports/pilot_regression/results.md`; no embeddings are generated here.
