# Third-party notices

ULTRON's own source is MIT-licensed — see [`LICENSE`](LICENSE).

It also **bundles and depends on software that is not ours**. Those licences are
listed here because several of them require the notice to travel with the code.

**If you redistribute ULTRON — a built dashboard, a disk image, a booth SD card,
a tarball — this file must travel with it.** It is not decoration; the SIL Open
Font License in §1 is only satisfied if the licence text and copyright notice
accompany the font files.

Nothing here is legal advice. It is an inventory, so that the person doing the
redistributing can check it.

---

## 1. Font Software — SIL Open Font License 1.1

The dashboard self-hosts four font families. `dashboard/web/scripts/build-fonts.py`
builds Latin subsets of them and writes `dashboard/web/src/styles/fonts.css`; the
resulting `.woff2` files are served from the Pi4 as first-party assets, not
fetched from a CDN.

Subsetting is mechanical: glyph subset plus woff2 re-encode. No glyph outlines are
redrawn and no family or reserved font name is changed. The derivatives therefore
stay under the OFL, as condition 5 requires.

### Newsreader

- Used for: the wordmark and display headings
- Upstream: <http://github.com/productiontype/Newsreader>
- Files served: `newsreader-*` (latin subset, weights as built)

```
Copyright 2020 The Newsreader Project Authors (http://github.com/productiontype/Newsreader)
Newsreader-Italic[opsz,wght].ttf: Copyright 2020 The Newsreader Project Authors (http://github.com/productiontype/Newsreader)
```

### Schibsted Grotesk

- Used for: UI and body text
- Upstream: <https://github.com/schibsted/schibsted-grotesk>
- Files served: `schibsted-grotesk-*` (latin subset, weights as built)

```
Copyright 2023 The Schibsted-Grotesk Project Authors (https://github.com/schibsted/schibsted-grotesk)
SchibstedGrotesk-Italic[wght].ttf: Copyright 2023 The Schibsted-Grotesk Project Authors (https://github.com/schibsted/schibsted-grotesk)
```

### JetBrains Mono

- Used for: telemetry, MACs, scores, and every other monospaced field
- Upstream: <https://github.com/JetBrains/JetBrainsMono>
- Files served: `jetbrains-mono-*` (latin subset, weights as built)

```
Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)
JetBrainsMono-Italic[wght].ttf: Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)
```

### IBM Plex Sans

- Used for: numeric and tabular readouts
- Upstream: <https://github.com/IBM/plex>
- Files served: `ibm-plex-sans-*` (latin subset, weights as built)

```
Copyright 2019 IBM Corp. All rights reserved.
```

### Licence text

All four are licensed under the SIL Open Font License, Version 1.1, reproduced
here in full as the licence requires. The original is available with a FAQ at
<https://scripts.sil.org/OFL>.

```
-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
```

---

## 2. Python packages — runtime (Pi4 governance node)

Pinned in `dashboard/server/requirements.txt`.

| Package | Version | Licence |
|---------|---------|---------|
| aiohttp | 3.10.10 | Apache-2.0 |
| aiomqtt | 2.3.0 | BSD-3-Clause |
| aiosqlite | 0.20.0 | MIT |
| webauthn | 3.0.1 | BSD-3-Clause |

Not resold and not modified; installed from wheels by `pip` at deploy time. The
Apache-2.0 packages include their own `NOTICE` files inside the wheels, which
`pip` installs alongside them.

## 3. Python packages — development and test only

Pinned in `requirements-dev.txt`. **Not present on a deployed Pi.**

| Package | Version | Licence |
|---------|---------|---------|
| pytest | 8.3.3 | MIT |
| pytest-asyncio | 0.24.0 | Apache-2.0 |
| paho-mqtt | 2.1.0 | EPL-2.0 OR BSD-3-Clause |
| pyserial | 3.5 | BSD-3-Clause |

`paho-mqtt` is dual-licensed; ULTRON takes it under **BSD-3-Clause**. `cbor2`
(MIT) and `cryptography` (Apache-2.0 OR BSD-3-Clause) appear only if the optional
ESP32 tooling is used.

## 4. Node packages — build-time only

Pinned in `dashboard/web/package.json`. **Nothing here ships in the browser
bundle except React.**

| Package | Version | Licence |
|---------|---------|---------|
| react, react-dom | 18.3.1 | MIT |
| vite | 5.4.10 | MIT |
| vitest | 2.1.8 | MIT |
| typescript | 5.6.3 | Apache-2.0 |
| @vitejs/plugin-react | 4.3.3 | MIT |
| @types/react, @types/react-dom | 18.3.x | MIT |
| @fontsource-variable/* | ^5.3.0 | MIT (package) — the fonts inside are OFL, §1 |

The `@fontsource` packages are MIT as *packaging*; the font binaries they carry
are the OFL Font Software listed in §1, and it is §1 that governs what is served.

---

## 5. Programs ULTRON invokes but does not link, modify or redistribute

This is the licensing boundary that matters most for ULTRON, and it is deliberate.

| Program | Licence | How ULTRON uses it |
|---------|---------|--------------------|
| **Suricata** | GPL-2.0 | Started as its own process by `systemd`; ULTRON reads its `eve.json` output. |
| **Mosquitto** | EPL-2.0 | Its own daemon; ULTRON is an MQTT *client* over TCP:1883. |
| **nftables / nft** | GPL-2.0 | Its own binary; ULTRON applies rules through `nft` and the kernel. |

ULTRON does not link against these, does not patch them, and does not ship them
in this repository. It talks to them across a process boundary or a socket. As a
consequence **their licences do not reach ULTRON's own source**, and ULTRON's MIT
licence does not reach them.

The practical consequences, which are worth knowing before you build a booth image:

- If you **redistribute a disk image** with Suricata or Mosquitto already
  installed, you are the one distributing GPL-2.0 and EPL-2.0 binaries. Ship
  their licences and, for the GPL-2.0 programs, be ready to supply the
  corresponding source — `apt-get source suricata` is normally enough.
- If you only **document** `apt-get install suricata mosquitto nftables`, no
  redistribution happens and no obligation attaches to you.
- This repository does neither: it documents the install in
  [`build.md`](build.md).

---

## 6. Deliberately absent

ULTRON has **no runtime JavaScript dependency beyond React**. The dashboard has no
CDN `<script>`, no font CDN, no analytics, no telemetry. That is a security
property before it is a licensing one — see the CSP notes in
[`SECURITY.md`](SECURITY.md) — but it also means the browser-side third-party
surface is close to empty.
