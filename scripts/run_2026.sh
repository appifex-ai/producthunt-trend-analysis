#!/usr/bin/env bash
set -euo pipefail

: "${PRODUCT_HUNT_TOKEN:?Set PRODUCT_HUNT_TOKEN to a Product Hunt API token}"

ph-trends sync --start 2026-01-01 --end 2027-01-01
ph-trends analyze --year 2026 --output reports/2026
ph-trends product Vokal
