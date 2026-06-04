# Security and Privacy Model

This project should be designed as metadata-first and customer-owned-data-first.

## Core rule

The platform should not require sensitive customer content to leave the customer environment.

## Data capture levels

### Level 0: Metadata only

Store only run metadata, source coverage, confidence, timestamps, decision types, quality gate status, and aggregate metrics.

### Level 1: Redacted evidence

Store evidence summaries with automatic redaction of PII, secrets, internal notes, and customer-sensitive fields.

### Level 2: Customer-hosted full evidence

Store detailed prompts, evidence, and traces only inside the customer-controlled environment.

### Level 3: Regulated deployment

Customer-owned VPC/VNet, customer-owned databases, customer-managed keys, private networking, audit logging, and strict RBAC.

## Public repo safety rules

- Do not include real customer names unless sourced from public information and legally safe.
- Do not include private CRM, Slack, support, or field notes.
- Do not include API keys, tokens, secrets, emails, or private URLs.
- Use synthetic companies in examples.
- Treat outreach as drafts only.
- Never auto-send messages.
- Never update CRM without human approval.

## Product opportunity

Security is not just a requirement; it is the enterprise wedge.

A good product should help customers answer:

- Which agents touched sensitive data?
- Which recommendations relied on low-confidence evidence?
- Which workflows produced unsupported claims?
- Which source systems were accessed?
- Which human approved an action?
