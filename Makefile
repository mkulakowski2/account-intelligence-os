validate-example:
	PYTHONPATH=src python -m account_intel.validate contracts/evidence_bundle.schema.json examples/sample_evidence_bundle.json

run-demo:
	PYTHONPATH=src python -m account_intel.run --account Datadog
