# AI Hub API reference

This reference documents the HTTP operations used by the AI Hub aihubshell v0.6 client. It is not a claim that these endpoints are a complete or permanently stable public API contract. Verify behavior against the official AI Hub guide before relying on it in production.

- API base URL: https://api.aihub.or.kr
- Download route version observed in aihubshell: 0.6
- Official guide: https://aihub.or.kr/devsport/apishell/list.do?currMenu=528&topMenu=100
- Shell guide PDF: https://www.aihub.or.kr/static/pdf/aihubshell_%EA%B0%80%EC%9D%B4%EB%93%9C.pdf

## Authentication

The shell implementation sends the API key only on download requests, in this HTTP header:

~~~http
apikey: YOUR_AI_HUB_API_KEY
~~~

The metadata list and detail requests in the shell do not include that header. The shell source declares a key-validation URL but does not call it in the request paths documented here; this project does not invent a separate validation operation.

Never place a real key in source control, a URL, a log, or an agent prompt. The bundled Python utility reads AIHUB_API_KEY from the environment.

## Metadata operations

| Purpose | Method | Path | API key in shell |
| --- | --- | --- | --- |
| List datasets | GET | /info/dataset.do | No |
| Get dataset file tree | GET | /info/{datasetKey}.do | No |
| List data packages | GET | /info/datapckage.do | No |
| Get package file tree | GET | /info/pckage/{packageKey}.do | No |

The API's published shell guide describes dataset/package identifiers, file names, sizes, file IDs, and notices in these responses. It does not publish complete response JSON Schemas. The OpenAPI document therefore uses an unconstrained JSON Schema for these bodies until representative responses can be captured and checked.

Example:

~~~bash
curl --fail-with-body 'https://api.aihub.or.kr/info/dataset.do'
curl --fail-with-body 'https://api.aihub.or.kr/info/593.do'
curl --fail-with-body 'https://api.aihub.or.kr/info/datapckage.do'
curl --fail-with-body 'https://api.aihub.or.kr/info/pckage/1.do'
~~~

## Download operations

| Resource | Method | Path |
| --- | --- | --- |
| Dataset files | GET | /down/0.6/{datasetKey}.do |
| Data package files | GET | /down/pckage/0.6/{packageKey}.do |

Both download routes require the apikey header and accept the file selector as the query parameter fileSn.

- Omit a selection in the user-facing workflow to download all files; the shell sends fileSn=all.
- Specify one or more file IDs as a comma-separated value, for example fileSn=51937,51938.
- The shell guide calls these identifiers filekey; the actual query parameter used by the shell source is fileSn.
- AI Hub may require a separate dataset/package request that states the intended purpose.
- The inspected shell API guide and supplied aihubshell source do not identify an approval-status query operation. This project has not verified whether another undocumented or account-specific endpoint exists.

Example:

~~~bash
curl --fail-with-body --location \
  --header "apikey: $AIHUB_API_KEY" \
  --output dataset-593.tar \
  'https://api.aihub.or.kr/down/0.6/593.do?fileSn=51937,51938'
~~~

Package download:

~~~bash
curl --fail-with-body --location \
  --header "apikey: $AIHUB_API_KEY" \
  --output package-1.tar \
  'https://api.aihub.or.kr/down/pckage/0.6/1.do?fileSn=all'
~~~

The shell extracts the downloaded TAR and merges files whose names end in .part followed by a numeric byte offset. The HTTP response's detailed headers, error schema, range/resume semantics, and all metadata response fields have not yet been independently verified. Do not assume resumable download support solely because the shell invokes curl with a continue option.

### Download failure and approval troubleshooting

The Python utility supports a machine-readable mode:

~~~bash
python skills/aihub-access/scripts/aihub.py --json download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data
~~~

On failure it exits with status 1 and emits a JSON object to stdout:

~~~json
{
  "ok": false,
  "command": "download",
  "error": {
    "code": "download_access_denied",
    "message": "AI Hub download request failed (HTTP 403).",
    "http_status": 403,
    "approval_check_recommended": true,
    "api_key_check_recommended": false,
    "next_action": "Check in your AI Hub account whether the download request for this dataset or package has been submitted and approved. AIHub4All does not currently verify approval status."
  }
}
~~~

The example illustrates the utility's output contract, not a confirmed AI Hub error payload. A 403 response or response text suggesting an approval/permission issue sets approval_check_recommended. This is only a troubleshooting hint; it does not establish that the request is missing or unapproved. A 401 response points the user toward checking the API key. Network failures and unrelated server errors do not automatically recommend an approval check.

## Endpoint naming caveats

The package endpoints contain the spelling pckage, and the package-list endpoint contains datapckage. These spellings are preserved because they are the observed server routes. Do not silently normalize them in clients.

## Evidence and verification status

| Item | Evidence | Status |
| --- | --- | --- |
| Route paths and HTTP methods | Supplied aihubshell v0.6 source | Observed |
| apikey request header | Supplied shell source and official guide examples | Observed |
| fileSn query parameter | Supplied shell source | Observed |
| fileSn=all behavior | Official shell guide and shell default | Documented |
| Download approval prerequisite | Official AI Hub guide | Documented |
| Metadata JSON structure | No complete published schema found | Unverified |
| Exact response media type and error bodies | Not captured from live API | Unverified |
| HTTP Range support | Not verified |
| Approval-status query operation | Not identified in the inspected shell API guide/source; other undocumented endpoints not ruled out | Unverified | Unverified |

Submit sanitized fixtures and verification notes before tightening the schemas.
