> **Status:** This document describes the proposed research, including future
> next-round prediction tasks and models. The current implementation only
> prepares pre-tournament and post-round interviews with stage labels and
> completed-round scores where applicable. See
> [README.md](README.md) for the implemented scope, workflow, and outputs.

# Introduction

Sports and performance predictions typically rely on statistics such as
rankings, recent scores, and historical results. However, athletes may
reveal additional information about their physical condition,
confidence, and preparation through interviews. This project
investigates whether a golfer's pre-tournament and post-round interviews can
help improve predictions of their next-round performance beyond what historical
statistics already indicate. Our goal is to determine whether language
provides useful predictive information and identify which types of
statements matter most.

# Related Work

@velichkov2019 used 50 pre-match interviews from tennis, boxing, and
martial arts to predict match outcomes. Comparing statistical features
with NLP methods including TF-IDF and BERT, their best model achieved
92% accuracy. They also identified language about physical condition,
expectations, and preparation as potentially predictive.

@oved2020 investigated whether NBA player interviews could predict
subsequent in-game behavior beyond historical statistics. Using 1,337
interviews, they developed neural models incorporating BERT,
question-answer structure, and attention. Combining interview language
with historical statistics improved prediction accuracy over
statistics-only baselines. The team nature of basketball does make it
slightly harder to model individual predictions.

@pastoriza2022 collected Tiger Woods' press conferences from 1996--2020
alongside tournament statistics. They used lexicon-based sentiment
analysis and performance-momentum features but did not develop
supervised models for predicting next-round outcomes.

A relevant model to our project is Sentence-Bert, introduced by
@reimers2019. It generates semantically meaningful sentence embeddings
using pretrained transformer encoders.

Our project extends these studies by predicting continuous and
categorical next-round golf performance and explicitly evaluating the
predictive contribution of forward-looking interview language.

# Proposed Approach

We propose a framework for predicting golfers' next-round performance
using pre-tournament and post-round interview language alongside historical
scoring statistics. Building on prior work in athlete interview analysis, we aim to
determine whether contextual language representations provide predictive
information beyond traditional performance measures and identify which
types of interview content are most informative.

We will formulate two prediction tasks:

1.  **Regression**: Predict the golfer's next-round score relative to
    the field average, accounting for differences in course difficulty
    and playing conditions. Pre-tournament interviews predict round 1;
    interviews after rounds 1–3 predict the following round.

2.  **Binary classification**: Predict whether the golfer will
    outperform their previous round in the same tournament, using interviews
    after rounds 1–3. Pre-tournament interviews are not used for this task
    because they have no completed round in the current event.

Our framework will use pretrained Sentence-BERT to generate contextual
embeddings of individual interview responses and question-answer pairs.
We will compare mean pooling with a trainable attention mechanism that
assigns different weights to interview segments, following the
structured interview modeling approach of @oved2020. These
representations will be combined with historical scoring features and
passed through regression or classification models, including MLPs. We
will also investigate supervised fine-tuning of the pretrained encoder
to learn task-specific language representations.

We will also investigate whether forward-looking language provides more
predictive information than general interview content. Motivated by
prior findings that statements about physical condition, expectations,
and preparation may contain predictive signals, we will identify
interview segments discussing confidence, physical condition,
preparation, strategy, and upcoming rounds. We will compare these
segments against full interviews and non-forward-looking content through
controlled comparisons and ablation experiments.

# Experimental Plan

## Data Collection

We will construct a dataset of pre-tournament and post-round interviews and
subsequent performance from PGA Tour individual stroke-play tournaments between
2015 and 2025. Each observation will represent one interview. The prepared
dataset records `interview_stage` as `pre_round_1` or `post_round_1` through
`post_round_4`; pre-tournament rows have an empty completed-round field and null
strokes. It retains final-round interviews and rows without future scores.
Regression examples will pair pre-tournament interviews with round 1 and
post-round 1–3 interviews with the following round. Classification examples
will use only post-round 1–3 interviews.

We will collect transcripts from ASAP Sports
(<https://www.asapsports.com/>), extracting player names, tournament
names, interview dates, and question-answer pairs. We will obtain
hole-by-hole scoring data from golfastR (<https://golfastr.com/>) and
aggregate these records into round-level scores. Interviews will be
matched to scoring records using player names, tournament identifiers,
and dates. Ambiguous matches will remain outside the prepared dataset.
Observations without a valid target-round score will be omitted when constructing
the prediction datasets. We define field-relative score as a golfer's
stroke total minus the average stroke total of all players in the same
tournament round, where lower values indicate better performance. This
allows us to compare performance across different courses and
tournaments. For regression, we will predict the golfer's next-round
field-relative score. For binary classification, we will predict whether
this score is better than the golfer's previous field-relative score in the
same tournament.

We will also construct statistical features available before the
predicted round, including current-round performance, current tournament
performance, and historical field-relative scoring averages. Pre-tournament
interviews can use historical features, but current-event performance statistics
will be missing. We will represent those missing values explicitly and choose
their model-specific handling during feature preparation, using training data
only for fitted transformations; missing scores will not be treated as zero.
Interview stage will be available as a feature and for reporting results by stage.

## Data Preprocessing

We will preserve the question-answer structure of each interview while
removing speaker labels, formatting artifacts, and non-interview
content.

We will construct three text representations:

1.  Full interviews containing all player responses, without questions

2.  Question-answer pairs that preserve conversational context

3.  Subsets of forward-looking statements discussing confidence,
    preparation, strategy, physical condition, and expectations for
    upcoming rounds

Forward-looking statements will initially be identified using rule-based
filtering of questions and responses. We will manually evaluate a sample
to assess extraction accuracy and retain non-forward-looking statements
for comparison.

We will initially use pretrained Sentence-BERT (`all-MiniLM-L6-v2`) to
generate 384-dimensional embeddings of interview segments. Longer
segments will be divided into shorter chunks to accommodate the
encoder's input length limit. Statistical features will be standardized
using training-set statistics.

## Model Configurations

#### Statistical and Linear Baselines.

We will train Ridge regression and logistic regression models using
historical performance statistics. We will also evaluate linear models
using mean-pooled interview embeddings, both independently and combined
with statistical features.

#### MLP Models.

We will implement MLPs using interview embeddings and optional
statistical features. The networks will use fully connected layers with
ReLU activations and dropout, followed by task-specific regression or
classification outputs. These models will test whether nonlinear
relationships improve predictions over linear baselines.

#### Attention-Based Interview Model.

Inspired by @oved2020, we will implement trainable attention over
interview segments. Rather than averaging all segment embeddings
equally, attention will assign learned weights to individual responses
or question-answer pairs. Their weighted combination will form an
interview-level representation, which will be concatenated with
statistical features and passed through an MLP prediction head. We will
compare this architecture against mean pooling while keeping other
components consistent.

#### Fine-Tuned Encoder.

We will investigate supervised fine-tuning of Sentence-BERT by allowing
gradients from the prediction loss to update the pretrained encoder. We
will compare frozen and fine-tuned representations under comparable
prediction architectures to evaluate the benefits of task-specific
language adaptation.

## Training and Evaluation

We will implement our models using Python, PyTorch,
SentenceTransformers, and scikit-learn. Neural models will be trained
using AdamW, with mean squared error for regression and binary
cross-entropy for classification. We will tune learning rates,
regularization, dropout, and hidden-layer dimensions using validation
data and apply early stopping to reduce overfitting.

We will randomly divide the dataset into approximately 80% training, 10%
validation, and 10% testing, grouping observations by tournament-year to
ensure that interviews from the same event remain within the same split.
Historical statistical features will be computed using only information
available before each interview to prevent data leakage.

For regression, we will report mean absolute error (MAE) and root mean
squared error (RMSE). For classification, we will report accuracy,
macro-F1, and ROC-AUC, comparing results against a majority-class
baseline.

We will conduct the following experiments:

1.  **Statistical vs. language-based prediction:** Compare
    statistics-only, language-only, and combined models to measure the
    added value of interview language.

2.  **Regression vs. classification:** Evaluate whether linguistic
    features are more useful for continuous performance prediction or
    predicting increase/decrease in performance.

3.  **Answer-only vs. question-answer representations:** Determine
    whether interviewer questions provide useful contextual information.

4.  **Mean pooling vs. attention:** Compare uniform averaging against
    learned attention-based aggregation of interview segments.

5.  **Frozen vs. fine-tuned embeddings:** Evaluate whether supervised
    encoder adaptation improves prediction accuracy.

6.  **Forward-looking language analysis:** Compare full interviews,
    forward-looking statements, and non-forward-looking statements. We
    will also remove selected categories of statements to evaluate their
    individual contributions.

7.  **Player-specific language control:** Shuffle interviews among
    players within the same tournament round to test whether
    improvements reflect player-specific language rather than shared
    tournament conditions.

Finally, we will conduct qualitative error analysis and examine
attention weights alongside language ablation results to investigate
which interview content contributes to predictions. Neural experiments
will be repeated across multiple random seeds to assess stability.
