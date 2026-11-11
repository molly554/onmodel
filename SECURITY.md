# Security

## Reporting a vulnerability

Please do not post details of a vulnerability in a public issue.

Open an issue titled "Security report" that says you have one and nothing else. A maintainer will reply with a private way to share the details. If GitHub's private vulnerability reporting is enabled for this repository (Security tab, "Report a vulnerability"), you can use that instead.

This is a small project maintained in spare time. We cannot promise a response time, but we will read every report.

## What the tool does with secrets and the network

- **Keys.** API keys are read from the environment (`GEMINI_API_KEY`) and are never printed, logged or written to a file. Run records contain file names and hashes, not paths or keys.
- **Network.** `onmodel check`, `analyze` and `bench judge` send your images to the reviewer you chose (by default Google's Gemini API). `bench run` sends images and prompts to the engine you chose. `bench fetch` downloads images only from an allow-list of hosts (Wikimedia and Open Beauty Facts), refuses redirects outside it, caps the size, and re-encodes what it downloads. No other command in the package makes a network call.
- **Downloaded files** are treated as untrusted data: checked against a recorded sha256, decoded and re-encoded as JPEG, never executed.
- **Your own engine or reviewer** (`--engine package.module:Class`, `--judge package.module:Class`) is Python code that runs with your permissions. Only load code you trust.
- **CI** has no secrets. It runs the tests, the asset gate and the link check offline.
