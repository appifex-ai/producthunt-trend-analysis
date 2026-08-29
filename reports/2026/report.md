# Product Hunt 2026 trend analysis

Analyzed **5,019 featured products** across **8 months**.
This report uses the full collected population, not a monthly top-N sample.
Vote and comment counts are cumulative snapshots collected through `2026-08-29T08:54:46.853813+00:00`.

## Dataset

| Month | Featured products | Median votes | Total votes |
|---|---:|---:|---:|
| 2026-01 | 432 | 131 | 80,517 |
| 2026-02 | 508 | 124 | 92,999 |
| 2026-03 | 677 | 124 | 119,157 |
| 2026-04 | 901 | 96 | 126,719 |
| 2026-05 | 827 | 95 | 115,508 |
| 2026-06 | 616 | 117 | 105,057 |
| 2026-07 | 534 | 137.5 | 100,275 |
| 2026-08 | 524 | 112.5 | 81,505 |

## Most common themes through 2026-08

- **Agent Identity**: 955 products
- **Harness Infrastructure**: 392 products
- **Coding And Building**: 268 products
- **Openclaw Ecosystem**: 113 products
- **Model Release**: 80 products
- **Human Agent Organization**: 77 products
- **Ai Coworkers**: 30 products
- **Gtm Agents**: 25 products
- **Loop Engineering**: 5 products

## Latest month (2026-08)

- **Agent identity**: 119/524 launches (22.7%); 15/53 in the top decile, 1.246x top-decile lift
- **Harness and infrastructure**: 55/524 launches (10.5%); 7/53 in the top decile, 1.258x top-decile lift
- **Coding and building**: 39/524 launches (7.4%); 6/53 in the top decile, 1.521x top-decile lift
- **Human-agent organization**: 9/524 launches (1.7%); 0/53 in the top decile, 0.0x top-decile lift
- **AI coworkers**: 6/524 launches (1.1%); 2/53 in the top decile, 3.296x top-decile lift
- **Model releases**: 6/524 launches (1.1%); 0/53 in the top decile, 0.0x top-decile lift
- **OpenClaw ecosystem**: 4/524 launches (0.8%); 1/53 in the top decile, 2.472x top-decile lift
- **GTM agents**: 3/524 launches (0.6%); 1/53 in the top decile, 3.296x top-decile lift
- **Loop engineering**: 1/524 launches (0.2%); 0/53 in the top decile, 0.0x top-decile lift

## Theme timelines

| Theme | First observed | Peak share | Peak lift | Latest share | Net change |
|---|---|---|---|---:|---:|
| Agent identity | 2026-01 | 2026-03 (22.7%) | 2026-06 (2.198x) | 22.7% | +10.7 pp |
| AI coworkers | 2026-02 | 2026-08 (1.1%) | 2026-06 (4.968x) | 1.1% | +0.8 pp |
| Coding and building | 2026-01 | 2026-03 (7.5%) | 2026-01 (2.888x) | 7.4% | +3.5 pp |
| GTM agents | 2026-01 | 2026-06 (0.6%) | 2026-06 (4.968x) | 0.6% | +0.3 pp |
| Harness and infrastructure | 2026-01 | 2026-08 (10.5%) | 2026-05 (1.911x) | 10.5% | +5.9 pp |
| Human-agent organization | 2026-01 | 2026-03 (2.1%) | 2026-05 (4.65x) | 1.7% | +0.8 pp |
| Loop engineering | 2026-03 | 2026-03 (0.4%) | 2026-03 (3.319x) | 0.2% | -0.2 pp |
| Model releases | 2026-01 | 2026-03 (2.4%) | 2026-02 (3.256x) | 1.1% | -0.9 pp |
| OpenClaw ecosystem | 2026-01 | 2026-03 (6.1%) | 2026-04 (4.57x) | 0.8% | +0.5 pp |

## External timeline anchors

- **2026-01-12**: Anthropic launched Cowork as a research preview ([source](https://www.anthropic.com/news/introducing-anthropic-labs))
- **2026-01-30**: The first OpenClaw-named GitHub release was published ([source](https://github.com/openclaw/openclaw/releases/tag/v2026.1.29))
- **2026-02-05**: OpenAI introduced Frontier as a platform for enterprise AI coworkers ([source](https://openai.com/index/introducing-openai-frontier/))
- **2026-05-13**: AI Harness Engineering formalized the model-harness-environment substrate ([source](https://arxiv.org/abs/2605.13357))
- **2026-06-02**: Vokal launched its shared collaboration space on Product Hunt ([source](https://www.producthunt.com/products/vokal-2))
- **2026-07-17**: IBM published its definition of loop engineering ([source](https://www.ibm.com/think/topics/loop-engineering))
- **2026-08-22**: A research review reported an exploratory study of loop engineering adoption ([source](https://arxiv.org/abs/2608.21884))

## Methodology

Posts are fetched from Product Hunt's GraphQL API with `featured: true`, partitioned into bounded monthly windows, and fully paginated. Categories are multi-label regex matches over name, tagline, description, and available topics. The top decile is recomputed independently for each month by current vote count.
Categories overlap because a launch may match multiple narratives. Top-decile lift measures representation among high-vote launches; it does not establish causation or equal-age launch performance.

Taxonomy version: `2026-08-29.4`.
