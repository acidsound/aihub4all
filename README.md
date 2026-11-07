# AIHub4All

**AI Hub for humans and agents.**

AIHub4All is an independent, open-source access toolkit for Korea's [AI Hub](https://aihub.or.kr). It brings human-readable guidance, a machine-readable OpenAPI 3.1 specification, reusable Agent Skills, and portable dataset download and processing utilities together.

The goal is to make AI Hub datasets easier to discover, understand, download, and prepare—whether you work directly as a researcher or delegate the workflow to an AI agent.

> **Independent community project.** AIHub4All is not affiliated with, endorsed by, or operated by the official AI Hub. AI Hub accounts, API keys, dataset approvals, and data-use conditions remain authoritative.

## What is included

| Component | Purpose | Status |
| --- | --- | --- |
| Human documentation | Explain discovery, authorization, download, and data processing | Initial |
| OpenAPI 3.1 | Describe the HTTP operations used by the published aihubshell client | Initial; metadata schemas need captured-response verification |
| Agent Skill | Give compatible agents a repeatable discovery-to-download workflow | Initial |
| Python utility | Query metadata, download TAR archives, safely extract them, and merge split files | Initial; live API testing pending |

## Quick start

### 1. Obtain an AI Hub API key

Create or sign in to your account at [AI Hub](https://aihub.or.kr), then request an API key from the AI Hub Open API page. AI Hub sends the key to the account email address according to its current process.

AI Hub's normal workflow may require a dataset-specific request that states the intended purpose before download. This project does not submit that request. The downloader does not query approval status: no approval-status operation has been verified in the shell API documentation. It attempts the download and, when an access-denied response suggests a permission issue, returns a structured hint to check the request in the AI Hub account. That hint is not proof that approval is missing.

### 2. Configure the key

The utility reads the key from the environment. Do not commit it, put it in a script, or paste it into an agent conversation.

~~~bash
export AIHUB_API_KEY='YOUR_API_KEY'
~~~

PowerShell:

~~~powershell
$env:AIHUB_API_KEY = 'YOUR_API_KEY'
~~~

### 3. Use the downloader

Requires Python 3.10 or later. The utility uses only the Python standard library.

~~~bash
# List datasets and inspect one dataset's file tree
python skills/aihub-access/scripts/aihub.py datasets
python skills/aihub-access/scripts/aihub.py dataset 593

# List data packages and inspect one package
python skills/aihub-access/scripts/aihub.py packages
python skills/aihub-access/scripts/aihub.py package 1

# Download selected file IDs
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data

# Download every file in an approved dataset
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --output-dir ./aihub-data

# Process an archive downloaded separately, or merge split files in a directory
python skills/aihub-access/scripts/aihub.py process ./download.tar \
  --output-dir ./aihub-data
python skills/aihub-access/scripts/aihub.py merge ./aihub-data
~~~

By default, a successful download is extracted and split parts are merged. Use --archive-only to keep the downloaded TAR without extracting it, or --keep-archive to retain the TAR after successful processing. Existing files are not overwritten.

For agent automation, put --json before the subcommand. The command writes one JSON result to stdout and progress messages to stderr:

~~~bash
python skills/aihub-access/scripts/aihub.py --json download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data
~~~

A failed download exits non-zero and returns an error object. When AI Hub responds with HTTP 403, or its response text indicates an approval/permission issue, error.approval_check_recommended is true and error.next_action tells the agent to ask the user to check the AI Hub website. HTTP 401 instead recommends checking the API key. These are troubleshooting hints; the tool does not know the actual approval state.

Before downloading a large dataset, inspect its file tree and available storage. AI Hub's guide recommends reserving roughly 2–3 times the download size for extraction and processing. The utility does not submit dataset-purpose requests, query approval status, or bypass AI Hub access controls.

## Agent Skills

The repository contains a portable Agent Skill in skills/aihub-access. It teaches compatible agents to discover datasets, check download prerequisites, invoke the bundled utility, and report the resulting files.

Install for OpenAI Codex and Claude Code:

~~~bash
# User-level installation
python scripts/install_skill.py

# Install into the current project instead
python scripts/install_skill.py --scope project

# Install only one target
python scripts/install_skill.py --targets codex
python scripts/install_skill.py --targets claude
~~~

The installer copies the same skill package to the native directories:
- OpenAI Codex: ~/.agents/skills/aihub-access
- Claude Code: ~/.claude/skills/aihub-access

Other Agent Skills-compatible tools may support their own discovery paths. The skill content itself follows the portable SKILL.md format; consult your agent's current documentation for its installation location.

## API specification

The OpenAPI document is at openapi/aihub.openapi.yaml.

It describes the metadata and download routes used by the published aihubshell v0.6 client. AI Hub's public guide does not provide complete machine-readable response schemas for the metadata endpoints. Those responses are therefore intentionally left unconstrained rather than guessed. Contributions of sanitized, representative responses are welcome.

See:
- [API reference](docs/api-reference.md)
- [Data processing guide](docs/data-processing.md)
- [Agent Skill](skills/aihub-access/SKILL.md)

## Development

Run the offline tests:

~~~bash
python -m unittest discover -s tests -v
~~~

The tests do not require an AI Hub API key and do not make network requests. Live API behavior, authorization failures, and large-file transfer behavior still need to be verified against real AI Hub accounts and approved datasets.

## Contributing

Useful contributions include:
- Sanitized metadata response fixtures and verified JSON Schemas
- Cross-platform tests for downloads and archive processing
- Documentation corrections based on current AI Hub behavior
- Agent Skill compatibility reports and additional install targets

Never submit API keys, personal data, private dataset contents, or unredacted account responses.

## License and data rights

The repository's code and documentation are licensed under the MIT License. This does not grant rights to AI Hub datasets. Dataset access, redistribution, and use remain subject to AI Hub's terms and each dataset's conditions.
