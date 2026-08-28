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

export AWS_ENDPOINT_URL ?= $(ENDPOINT)
export AWS_DEFAULT_REGION ?= us-east-1
export AWS_ACCESS_KEY_ID ?= test
export AWS_SECRET_ACCESS_KEY ?= test
export AWS_EC2_METADATA_DISABLED ?= true

.PHONY: help install up down logs health infra infra-plan destroy seed pipeline ingest silver gold query outputs test clean

help:
	@printf '%s\n' \
	  'Targets:' \
	  '  make install   editable install of src/lakehouse (+ dev extras)' \
	  '  make up        start MiniStack and wait until healthy' \
	  '  make health    probe MiniStack + list buckets/tables' \
	  '  make infra     terraform apply buckets + DynamoDB tables' \
	  '  make outputs   print Terraform outputs as KEY=value env vars' \
	  '  make seed      write synthetic events to bronze' \
	  '  make pipeline  bronze -> silver -> gold (local runner)' \
	  '  make ingest    drain Bronze SQS queue through the ingest handler' \
	  '  make silver    cleanse Bronze → Silver (+ quarantine) via the Silver handler' \
	  '  make gold      aggregate Silver → Gold metrics via the Gold handler' \
	  '  make query     print gold object + metrics summary' \
	  '  make test      unit tests' \
	  '  make down      stop MiniStack' \
	  '  make destroy   terraform destroy (keeps MiniStack running)' \
	  '  make clean     stop stack and remove local terraform state'

install:
	$(PIP) install -e "$(ROOT)[dev]"

up:
	@command -v docker >/dev/null || { echo "ERROR: docker is required for make up" >&2; exit 1; }
	$(COMPOSE) up -d
	@$(ROOT)/scripts/wait_healthy.sh
	@$(MAKE) --no-print-directory health

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --tail=100 ministack

health:
	@$(ROOT)/scripts/wait_healthy.sh
	@$(PYTHON) -m lakehouse health

infra-plan:
	@command -v terraform >/dev/null || { echo "ERROR: terraform is required for make infra" >&2; exit 1; }
	@$(ROOT)/scripts/wait_healthy.sh
	cd $(TF_DIR) && terraform init -input=false
	cd $(TF_DIR) && terraform plan -input=false -out=tfplan

infra:
	@command -v terraform >/dev/null || { echo "ERROR: terraform is required for make infra" >&2; exit 1; }
	@$(ROOT)/scripts/wait_healthy.sh
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
	@$(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse seed

pipeline:
	@$(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse pipeline

ingest:
	@$(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse ingest

silver:
	@$(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse silver

gold:
	@$(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse gold

query:
	@$(ROOT)/scripts/wait_healthy.sh
	@eval "$$(bash $(ROOT)/scripts/get_outputs.sh --tf-dir $(TF_DIR))"; $(PYTHON) -m lakehouse query

test:
	$(PYTHON) -m pytest $(ROOT)/tests

clean: down
	rm -rf $(TF_DIR)/.terraform $(TF_DIR)/terraform.tfstate $(TF_DIR)/terraform.tfstate.backup $(TF_DIR)/tfplan
