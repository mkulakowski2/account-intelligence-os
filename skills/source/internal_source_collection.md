# Skill: internal_source_collection

## Purpose

Collect internal account truth and first-party engagement history.

## Sources

- CRM
- collaboration tools
- docs and knowledge bases
- support / CS systems, if available

## Output

Return evidence bundle records only. Do not summarize into final report prose.

## Required Fields

- CRM account record
- opportunity history
- contacts
- notes
- collaboration tools mentions by channel
- Notion/docs references
- support or trial signals

## the selected agent runtime Skill Prompt

```text
You are running internal_source_collection for {{ACCOUNT_NAME}}.

Search only internal sources available to the current user.
Return structured evidence bundle records.
If a source is unavailable, mark it unavailable.
If no results are found, record "No results found as of {{DATE}}".
Do not write final report prose.
```
