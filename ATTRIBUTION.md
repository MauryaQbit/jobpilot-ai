# Attribution

**JobPilot AI** is a substantially modified and independently developed project
derived from the open-source **ai-job-scraper** project.

## Upstream project

- **Project:** ai-job-scraper
- **Author:** Bjorn Melin
- **Source:** https://github.com/BjornMelin/ai-job-scraper
- **License:** MIT

## Copyright notice (as required by the MIT License)

Copyright (c) 2025 Bjorn Melin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Scope of the derivation

The original project was rebuilt as JobPilot AI: a new `jobpilot` package
replaces the legacy `src` package, the job pipeline was rewritten (discovery,
normalization, deduplication, AI analysis, matching, and application tracking),
and the dashboard, CLI, and API were redesigned. Certain behaviors and
contracts from the upstream project are preserved for compatibility:

- The atomic saved-search run claim / record contract.
- The cost and budget monitoring model.
- The library-first, provider-row conversion strategy in the scraping layer.

The original MIT license and copyright notice are preserved in this file and
in [`LICENSE`](LICENSE).