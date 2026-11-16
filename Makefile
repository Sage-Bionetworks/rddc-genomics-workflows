# Local development and CI helpers. Pipelines run on Cirro from their tags; nothing here is
# needed there. Requires Docker; `make tools` fetches Nextflow into .tools/.

SHELL            := /bin/bash
NXF_VERSION      ?= 26.10.5
export NXF_HOME  ?= $(CURDIR)/.tools/nxf-home
export NXF_VER   := $(NXF_VERSION)
NEXTFLOW         := $(CURDIR)/.tools/nextflow

# rddc-reports image: modules pin ghcr.io/sage-bionetworks/rddc-reports:<version>. Building
# locally with that tag lets Nextflow use it without pulling.
REPORTS_DIR      := containers/rddc-reports
REPORTS_VERSION  := $(shell sed -n 's/^version = "\(.*\)"/\1/p' $(REPORTS_DIR)/pyproject.toml)
REPORTS_IMAGE    := ghcr.io/sage-bionetworks/rddc-reports:$(REPORTS_VERSION)
RF_TESTS         := tests/report-findings
RDDC_MODEL       ?= ../rddc-model

.PHONY: help tools lint image image-test py-test py-test-live py-test-seqrepo refdata-test fixtures \
        rf-stub rf-test fastq-stub fastq-test check-image-tags

help:   ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t 18

tools: $(NEXTFLOW)   ## fetch Nextflow into .tools/
$(NEXTFLOW):
	mkdir -p $(dir $@)
	curl -fsSL https://get.nextflow.io -o $@ && chmod +x $@ && $@ -version >/dev/null

lint: tools   ## nextflow lint for every pipeline, module and subworkflow
	$(NEXTFLOW) lint pipelines/*/main.nf modules subworkflows

image:   ## build the rddc-reports runtime image with the tag the modules pin
	docker build --target runtime -t $(REPORTS_IMAGE) $(REPORTS_DIR)

image-test:
	docker build --target test -t rddc-reports:test $(REPORTS_DIR)

py-test: image-test   ## rddc-reports unit tests, in the image, without network
	docker run --rm --network none -v $(CURDIR):/repo:ro rddc-reports:test

py-test-live: image-test   ## compare the reference subset with live UTA/NCBI (network)
	docker run --rm -e RDDC_REPORTS_LIVE=1 -v $(CURDIR):/repo:ro \
	    -v $(HOME)/.cache/rddc-reports:/root/.cache/rddc-reports rddc-reports:test

SEQREPO ?= ../seqrepo/2024-12-20
py-test-seqrepo: image-test   ## the same tests with sequences from a local SeqRepo ($(SEQREPO)), no network
	docker run --rm --network none -v $(CURDIR):/repo:ro -v $(abspath $(SEQREPO)):/seqrepo/$(notdir $(abspath $(SEQREPO))):ro \
	    -e RDDC_REPORTS_SEQREPO=/seqrepo/$(notdir $(abspath $(SEQREPO))) \
	    $(if $(REFDATA),-v $(abspath $(REFDATA)):/refdata/$(notdir $(REFDATA)):ro -e RDDC_REPORTS_REFDATA=/refdata/$(notdir $(REFDATA))) \
	    rddc-reports:test

refdata-test: image   ## rebuild tests/report-findings/refdata/subset.sqlite (public UTA + NCBI)
	docker run --rm -v $(CURDIR)/$(RF_TESTS)/refdata:/out -v $(HOME)/.cache/rddc-reports:/root/.cache/rddc-reports \
	    $(REPORTS_IMAGE) rddc-reports -v refdata build-subset --transcripts /out/transcripts.txt --out /out/subset.sqlite

fixtures:   ## regenerate the test sidecars and validate against rddc-model ($(RDDC_MODEL))
	python3 -I $(RF_TESTS)/make_sidecar.py --context $(RDDC_MODEL)/examples/ccda_document_set.json \
	    --schema $(RDDC_MODEL)/schema/generated/rddc_sidecar.schema.json

rf-stub: tools image   ## report-findings stub run (stubs still run in the image)
	$(NEXTFLOW) run . -main-script pipelines/report-findings/main.nf -profile test,docker -stub-run \
	    --sidecar $(RF_TESTS)/batch/_sidecar.json --refdata $(RF_TESTS)/refdata/subset.sqlite --outdir results/report-findings-stub

rf-test: tools image   ## report-findings on the test batch, and on the intake rejection cases
	$(NEXTFLOW) run . -main-script pipelines/report-findings/main.nf -profile test,docker \
	    --sidecar $(RF_TESTS)/batch/_sidecar.json --refdata $(RF_TESTS)/refdata/subset.sqlite --outdir results/report-findings
	diff <(tail -n +2 results/report-findings/intake/intake.tsv) <(tail -n +2 $(RF_TESTS)/expected/intake.tsv)
	$(NEXTFLOW) run . -main-script pipelines/report-findings/main.nf -profile test,docker \
	    --sidecar $(RF_TESTS)/batch/_sidecar.errors.json --outdir results/report-findings-errors
	diff <(tail -n +2 results/report-findings-errors/intake/intake.tsv) <(tail -n +2 $(RF_TESTS)/expected/intake.errors.tsv)

fastq-stub: tools   ## fastq-qc stub run
	$(NEXTFLOW) run . -main-script pipelines/fastq-qc/main.nf -profile test,docker -stub-run \
	    --input tests/fastq-qc/samplesheet.csv

fastq-test: tools   ## fastq-qc on the test data
	$(NEXTFLOW) run . -main-script pipelines/fastq-qc/main.nf -profile test,docker \
	    --input tests/fastq-qc/samplesheet.csv

check-image-tags:   ## modules must pin the rddc-reports version in pyproject.toml
	@bad=$$(grep -rhoE 'rddc-reports:[^'"'"'" ]+' modules | sort -u | grep -vx 'rddc-reports:$(REPORTS_VERSION)'); \
	    if [ -n "$$bad" ]; then echo "modules pin $$bad, pyproject.toml says $(REPORTS_VERSION)"; exit 1; fi
