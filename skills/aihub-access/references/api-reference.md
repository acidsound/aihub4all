# AI Hub API notes for agents

These notes describe observed behavior from the supplied aihubshell v0.6 source and the official AI Hub shell guide. They are not a complete official API contract.

Base URL: https://api.aihub.or.kr

## Metadata

| Action | Request |
| --- | --- |
| List datasets | GET /info/dataset.do |
| Dataset file tree | GET /info/{datasetKey}.do |
| List data packages | GET /info/datapckage.do |
| Package file tree | GET /info/pckage/{packageKey}.do |

The shell does not attach the API key to these metadata requests. Their complete JSON response schemas are not published in the guide; inspect returned data and do not assume field names beyond what is actually present.

## Downloads

Dataset:
- GET /down/0.6/{datasetKey}.do
- Header: apikey: API_KEY
- Query: fileSn=all or a comma-separated list of file IDs

Data package:
- GET /down/pckage/0.6/{packageKey}.do
- Header: apikey: API_KEY
- Query: fileSn=all or a comma-separated list of file IDs

The shell guide's CLI calls the selectable identifier filekey; the HTTP parameter observed in the shell is fileSn. AI Hub's workflow may require a separate request explaining the intended purpose. No approval-status query operation was identified in the inspected shell API guide/source; other undocumented endpoints are not ruled out.

The downloader's --json mode returns a machine-readable failure. For HTTP 403 or response text that suggests a permission/approval issue, error.approval_check_recommended is true and error.next_action directs the agent to have the user check the request in their AI Hub account. This is not a determination that approval is missing. HTTP 401 recommends checking the API key instead.

## Processing

The server response is a TAR archive in the observed shell workflow. Extract it while preserving directories, then merge files named filename.partN. N is treated as a byte offset. Check that offsets are contiguous with the accumulated byte count before removing source parts.

Official user guide: https://aihub.or.kr/devsport/apishell/list.do?currMenu=528&topMenu=100
