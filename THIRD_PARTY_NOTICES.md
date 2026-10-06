# Third-party notices

OSINT-Fire is released under the MIT License (see `LICENSE`). The packaged app (`dist/OSINT-Fire.app`) bundles the Python
packages below, each under its own license, and the Flutter engine and packages listed at the end.

Notes
- **pycountry** (LGPL-2.1) is a dependency of Maigret. It is pure Python and is shipped unmodified as replaceable files, so the
  LGPL conditions are met; you can swap it by rebuilding the app with another version.
- **PyInstaller** (GPL-2.0 with a special exception) freezes the backend; the exception allows distributing the result under any license.
- **certifi** is MPL-2.0 and is used unmodified.
- OSINT-Fire does not bundle or import theHarvester (GPL); it is only run, if the user installed it, as a separate program.
- Data sources are queried through their public or documented APIs under their own terms; no data from them is redistributed with the app.

## Python packages (backend)

| Package | Version | License |
|---|---|---|
| about-time | 4.2.1 | MIT |
| aiodns | 4.0.4 | MIT |
| aiohappyeyeballs | 2.7.1 | PSF-2.0 |
| aiohttp | 3.14.3 | Apache-2.0 AND MIT |
| aiohttp_socks | 0.12.0 | Apache-2.0 |
| aiosignal | 1.4.0 | Apache 2.0 |
| alive-progress | 3.3.0 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| asgiref | 3.12.1 | BSD-3-Clause |
| asttokens | 3.0.2 | Apache 2.0 |
| attrs | 26.1.0 | MIT |
| beautifulsoup4 | 4.15.0 | MIT License |
| blinker | 1.9.0 | MIT License |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | BSD License |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| curl_cffi | 0.16.3 | MIT |
| dnspython | 2.8.0 | ISC |
| executing | 2.2.1 | MIT |
| fastapi | 0.142.2 | MIT |
| Flask | 3.1.3 | BSD-3-Clause |
| frozenlist | 1.8.0 | Apache-2.0 |
| graphemeu | 0.7.2 | see package |
| h11 | 0.16.0 | MIT |
| html5lib | 1.1 | MIT License |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| httpx2 | 2.13.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| ipython | 9.17.1 | BSD-3-Clause |
| ipython_pygments_lexers | 1.1.1 | BSD License |
| itsdangerous | 2.2.0 | BSD License |
| jedi | 0.20.0 | MIT |
| Jinja2 | 3.1.6 | BSD License |
| jsonpickle | 4.1.3 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| maigret | 0.6.6 | MIT |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| matplotlib-inline | 0.2.2 | BSD-3-Clause |
| mcp | 2.3.0 | MIT |
| mcp-types | 2.3.0 | MIT |
| multidict | 6.9.1 | Apache License 2.0 |
| networkx | 2.8.8 | BSD License |
| opentelemetry-api | 1.45.0 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| parso | 0.8.7 | MIT |
| pexpect | 4.9.0 | ISC license |
| phonenumbers | 9.0.40 | Apache-2.0 |
| pillow | 12.3.0 | MIT-CMU |
| platformdirs | 4.12.3 | MIT |
| pluggy | 1.6.0 | MIT |
| prompt_toolkit | 3.0.53 | BSD License |
| propcache | 0.5.4 | Apache-2.0 |
| psutil | 7.2.2 | BSD-3-Clause |
| ptyprocess | 0.7.0 | ISC |
| pure_eval | 0.2.4 | MIT |
| pycares | 5.1.0 | MIT |
| pycountry | 26.2.16 | LGPL-2.1-only |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic_core | 2.46.5 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| PyJWT | 2.15.1 | MIT |
| PySocks | 1.7.1 | BSD |
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| python-dateutil | 2.9.0.post0 | Dual License |
| python-multipart | 0.0.32 | Apache-2.0 |
| python-socks | 3.1.1 | Apache-2.0 |
| pyvis | 0.3.2 | BSD |
| referencing | 0.37.0 | MIT |
| reportlab | 5.0.1 | BSD License |
| requests | 2.34.2 | Apache-2.0 |
| rpds-py | 2026.9.1 | MIT |
| six | 1.17.0 | MIT |
| socid-extractor | 0.1.1 | MIT |
| soupsieve | 2.10 | MIT |
| sse-starlette | 3.5.0 | BSD-3-Clause |
| stack-data | 0.6.3 | MIT |
| starlette | 1.7.0 | BSD-3-Clause |
| traitlets | 5.16.1 | BSD License |
| truststore | 0.10.4 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| wcwidth | 0.9.2 | MIT License |
| webencodings | 0.6.1 | BSD License |
| Werkzeug | 3.1.9 | BSD-3-Clause |
| XMind | 1.2.0 | MIT |
| yarl | 1.25.1 | Apache-2.0 |
## Flutter / Dart (app)

Flutter and the Dart SDK are BSD-3-Clause (Google). Direct dependencies: `http` (BSD-3-Clause, Dart project authors),
`cupertino_icons` (MIT). Their transitive Dart dependencies are BSD-3-Clause or MIT; see `app/pubspec.lock`.
Fonts: the interface uses the system monospace font (Menlo) and bundles no font files.

