# Local-first medallion lakehouse targets.
# Typical flow: make up && make infra && make seed && make pipeline && make query && make test

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
COMPOSE := docker compose -f $(ROOT)/docker-compose.yml
TF_DIR := $(ROOT)/infra/terraform
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
ENDPOINT ?= http://localhost:4566
LAMBDA_ZIP := $(ROOT)/build/lambda/lakehouse.zip

export AWS_ENDPOINT_URL ?= $(ENDPOINT)
export AWS_DEFAULT_REGION ?= us-east-1
export AWS_ACCESS_KEY_ID ?= test
export AWS_SECRET_ACCESS_KEY ?= test
export AWS_EC2_METADATA_DISABLED ?= true

.PHONY: help install up down logs health package infra infra-plan destroy seed pipeline ingest silver quality quality-dashboard gold sfn sfn-def query catalog dbt ui demo runs outputs reprocess lineage sla retention quarantine-retention quarantine-compact quarantine-maintain bronze-retention bronze-compact bronze-maintain silver-retention silver-compact silver-maintain compact maintain platform-maintain test test-integration ci lint pre-commit security clean

help:
	@printf '%s\n' \
	  'Targets:' \
	  '  make install   editable install of src/lakehouse (+ dev extras)' \
	  '  make up        start MiniStack and wait until healthy' \
	  '  make health    probe MiniStack + list buckets/tables' \
	  '  make package   zip lakehouse + pydantic for Lambda deploy' \
	  '  make infra     terraform apply buckets + DynamoDB + Lambdas + SFN' \
	  '  make outputs   print Terraform outputs as KEY=value env vars' \
	  '  make seed      write synthetic events to bronze' \
	  '  make pipeline  bronze -> silver -> gold (local runner)' \
	  '  make ingest    drain Bronze SQS queue through the ingest handler' \
	  '  make silver    cleanse Bronze to Silver via the Silver handler' \
	  '  make quality   run the Silver quality gate (fail or quarantine)' \
	  '  make gold      aggregate Silver to Gold metrics via the Gold handler' \
	  '  make sfn       walk the Step Functions graph via zone handlers' \
	  '  make sfn-def   print the medallion ASL definition' \
	  '  make query     print gold object + metrics summary' \
	  '  make catalog   describe / register Glue Silver and Gold tables' \
	  '  make dbt       parse and lint transform/dbt Gold models' \
	  '  make ui        write build/query-ui.html (Gold + named Athena SQL)' \
	  '  make quality-dashboard  write build/quality-dashboard.html' \
	  '  make lineage   write build/lineage.mmd (zone graph)' \
	  '  make sla       evaluate Gold freshness SLA' \
	  '  make retention plan Gold partition expiry (dry-run)' \
	  '  make quarantine-retention plan Silver quarantine TTL (dry-run)' \
	  '  make quarantine-compact plan Silver quarantine compact / rewrite (dry-run)' \
	  '  make quarantine-maintain Quarantine expire-then-compact (dry-run)' \
	  '  make bronze-retention plan Bronze raw event expiry (dry-run)' \
	  '  make bronze-compact plan Bronze raw-object compact / rewrite (dry-run)' \
	  '  make silver-retention plan Silver cleaned-event expiry (dry-run)' \
	  '  make compact    plan Gold metric-object compact / rewrite (dry-run)' \
	  '  make bronze-maintain Bronze expire-then-compact (dry-run)' \
	  '  make silver-compact plan Silver object compact / rewrite (dry-run)' \
	  '  make silver-maintain Silver expire-then-compact (dry-run)' \
	  '  make maintain   Gold expire-then-compact (dry-run)' \
	  '  make platform-maintain Bronze+Silver+Gold expire-then-compact (dry-run)' \
	  '  make demo      seed → pipeline → query with assertions' \
	  '  make runs      list pipeline run metadata from DynamoDB' \
	  '  make reprocess rebuild Gold for LOOKBACK_DAYS (late arrivals)' \
	  '  make test      unit + hermetic zone-path tests' \
	  '  make test-integration  live MiniStack Bronze to Silver to Gold' \
	  '  make lint      ruff check + format check' \
	  '  make pre-commit  run .pre-commit-config.yaml hooks on the whole tree' \
	  '  make security  hermetic secret scan + Checkov/Trivy when installed' \
	  '  make ci        lint + unit + up + infra + seed + pipeline + integration' \
	  '  make down      stop MiniStack' \
	  '  make destroy   terraform destroy (keeps MiniStack running)' \
	  '  make clean     stop stack and remove local terraform state'

install:
	$(PIP) install -e "$(ROOT)[dev]"

up:
	@command -v docker >/dev/null || { echo "ERROR: docker is required for make up" >&2; exit 1; }
	$(COMPOSE) pull --quiet || true
	$(COMPOSE) up -d --remove-orphans
	@bash $(ROOT)/scripts/wait_healthy.sh
	@$(MAKE) --no-print-directory health || true

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --tail=100 ministack

health:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@$(PYTHON) -m lakehouse health

package:
	$(PYTHON) $(ROOT)/scripts/package_lambda.py --out $(LAMBDA_ZIP)

infra-plan: package
	@command -v terraform >/dev/null || { echo "ERROR: terraform is required for make infra" >&2; exit 1; }
	@bash $(ROOT)/scripts/wait_healthy.sh
	cd $(TF_DIR) && terraform init -input=false
	cd $(TF_DIR) && terraform plan -input=false -out=tfplan

infra: package
	@command -v terraform >/dev/null || { echo "ERROR: terraform is required for make infra" >&2; exit 1; }
	@bash $(ROOT)/scripts/wait_healthy.sh
	cd $(TF_DIR) && terraform init -input=false
	cd $(TF_DIR) && terraform apply -input=false -auto-approve
	@echo "--- terraform outputs ---"
	@$(MAKE) --no-print-directory outputs

destroy:
	@command -v terraform >/dev/null || { echo "ERROR: terraform is required" >&2; exit 1; }
	cd $(TF_DIR) && terraform destroy -input=false -auto-approve

outputs:
	@bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR)

seed:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse seed

pipeline:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse pipeline

ingest:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse ingest

silver:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse silver

quality:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse quality

gold:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse gold

sfn:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse sfn

sfn-def:
	@$(PYTHON) -m lakehouse sfn-def

query:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse query

catalog:
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse catalog

dbt:
	@$(PYTHON) -m lakehouse dbt

ui:
	@$(PYTHON) -m lakehouse ui --out $(ROOT)/build/query-ui.html

quality-dashboard:
	@$(PYTHON) -m lakehouse quality-dashboard --out $(ROOT)/build/quality-dashboard.html

lineage:
	@$(PYTHON) -m lakehouse lineage --out $(ROOT)/build/lineage.mmd

sla:
	@$(PYTHON) -m lakehouse sla

RETENTION_DAYS ?=
retention:
	@$(PYTHON) -m lakehouse retention $(if $(RETENTION_DAYS),--retention-days $(RETENTION_DAYS),)

quarantine-retention:
	@$(PYTHON) -m lakehouse quarantine-retention $(if $(QUARANTINE_RETENTION_DAYS),--retention-days $(QUARANTINE_RETENTION_DAYS),)

QUARANTINE_COMPACT_MAX_OBJECTS ?=
quarantine-compact:
	@$(PYTHON) -m lakehouse quarantine-compact $(if $(QUARANTINE_COMPACT_MAX_OBJECTS),--max-objects $(QUARANTINE_COMPACT_MAX_OBJECTS),)

quarantine-maintain:
	@$(PYTHON) -m lakehouse quarantine-maintain $(if $(QUARANTINE_RETENTION_DAYS),--retention-days $(QUARANTINE_RETENTION_DAYS),) $(if $(QUARANTINE_COMPACT_MAX_OBJECTS),--max-objects $(QUARANTINE_COMPACT_MAX_OBJECTS),)

bronze-retention:
	@$(PYTHON) -m lakehouse bronze-retention $(if $(BRONZE_RETENTION_DAYS),--retention-days $(BRONZE_RETENTION_DAYS),)

BRONZE_COMPACT_MAX_OBJECTS ?=
bronze-compact:
	@$(PYTHON) -m lakehouse bronze-compact $(if $(BRONZE_COMPACT_MAX_OBJECTS),--max-objects $(BRONZE_COMPACT_MAX_OBJECTS),)

silver-retention:
	@$(PYTHON) -m lakehouse silver-retention $(if $(SILVER_RETENTION_DAYS),--retention-days $(SILVER_RETENTION_DAYS),)

GOLD_COMPACT_MAX_OBJECTS ?=
compact:
	@$(PYTHON) -m lakehouse compact $(if $(GOLD_COMPACT_MAX_OBJECTS),--max-objects $(GOLD_COMPACT_MAX_OBJECTS),)

bronze-maintain:
	@$(PYTHON) -m lakehouse bronze-maintain $(if $(BRONZE_RETENTION_DAYS),--retention-days $(BRONZE_RETENTION_DAYS),) $(if $(BRONZE_COMPACT_MAX_OBJECTS),--max-objects $(BRONZE_COMPACT_MAX_OBJECTS),)

SILVER_COMPACT_MAX_OBJECTS ?=
silver-compact:
	@$(PYTHON) -m lakehouse silver-compact $(if $(SILVER_COMPACT_MAX_OBJECTS),--max-objects $(SILVER_COMPACT_MAX_OBJECTS),)

silver-maintain:
	@$(PYTHON) -m lakehouse silver-maintain $(if $(SILVER_RETENTION_DAYS),--retention-days $(SILVER_RETENTION_DAYS),) $(if $(SILVER_COMPACT_MAX_OBJECTS),--max-objects $(SILVER_COMPACT_MAX_OBJECTS),)

maintain:
	@$(PYTHON) -m lakehouse maintain $(if $(RETENTION_DAYS),--retention-days $(RETENTION_DAYS),) $(if $(GOLD_COMPACT_MAX_OBJECTS),--max-objects $(GOLD_COMPACT_MAX_OBJECTS),)

platform-maintain:
	@$(PYTHON) -m lakehouse platform-maintain

demo:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; \
	  $(PYTHON) -m lakehouse demo --mode live

runs:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse runs

LOOKBACK_DAYS ?= 2
AS_OF ?=
reprocess:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; \
	  $(PYTHON) -m lakehouse reprocess --lookback-days $(LOOKBACK_DAYS) $(if $(AS_OF),--as-of $(AS_OF),)

test:
	$(PYTHON) -m pytest $(ROOT)/tests -m "not integration"

test-integration:
	@bash $(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; LAKEHOUSE_LIVE=1 $(PYTHON) -m pytest $(ROOT)/tests -m integration

lint:
	$(PYTHON) -m ruff check $(ROOT)/src $(ROOT)/tests $(ROOT)/scripts
	$(PYTHON) -m ruff format --check $(ROOT)/src $(ROOT)/tests $(ROOT)/scripts

pre-commit:
	$(PYTHON) -m pre_commit run --all-files --show-diff-on-failure

security:
	bash $(ROOT)/scripts/security_scan.sh

ci: lint test security up infra seed pipeline query test-integration

clean: down
	rm -rf $(TF_DIR)/.terraform $(TF_DIR)/terraform.tfstate $(TF_DIR)/terraform.tfstate.backup $(TF_DIR)/tfplan $(ROOT)/build/lambda
