/**
 * Curated intel behind every event the rig can raise.
 *
 * The feed shows a title and a sentence — enough to scan, not enough to act on.
 * Hovering or focusing a row opens a floating box carrying what an analyst
 * actually asks next: which tool produced the finding, the signature and sid
 * Suricata matched, the CVE, the MITRE ATT&CK technique, the ports involved,
 * and a plain statement of what the evidence does *not* prove.
 *
 * Rules are matched in order against the alert title, so a device label
 * ("IP camera", "Smart plug") can change without breaking a match. Keep the
 * patterns in step with the titles emitted by dashboard/tools/mock_feed.py and
 * dashboard/web/src/lib/simulation.ts — the same contract that already binds
 * LAN_DEVICES to IOT_DEVICES.
 *
 * All of it is drill fixture data. The signature names and sids are
 * illustrative rather than copies of a live ruleset, and the CVE ids name the
 * class of flaw being narrated rather than a scan result from this rig.
 */

export interface EventIntel {
  /** Detector class, used as the box's heading. */
  kind: string;
  /** The tool or observation source that produced the event. */
  tool?: string;
  /** The exact command line, when the event came from one. */
  command?: string;
  /** Signature or rule name that matched. */
  rule?: string;
  /** Signature id. */
  sid?: number;
  /** Protocol. */
  proto?: string;
  /** Ports, as one readable set. */
  ports?: string;
  /** CVE ids implicated. */
  cve?: string;
  /** MITRE ATT&CK technique, "Txxxx · Name". */
  mitre?: string;
  /** What the event means. One sentence. */
  means: string;
  /** What it does not prove. One sentence. */
  caution?: string;
}

interface Rule {
  match: RegExp;
  intel: EventIntel;
}

const RULES: Rule[] = [
  // -- drill control --------------------------------------------------------
  {
    match: /incident drill/i,
    intel: {
      kind: "Drill control",
      tool: "ultron simulate",
      command: "./simulate.sh stress",
      proto: "MQTT",
      ports: "1883/TCP",
      means:
        "An operator-started scenario, not a sensor reading. The rig is replaying a prepared attack chain so the detectors, the vault and the notification path are all exercised in one pass.",
      caution:
        "Any score or band in this run is scripted. Nothing here says the monitored LAN was attacked.",
    },
  },
  {
    match: /narrating the home LAN/i,
    intel: {
      kind: "Drill control",
      tool: "ultron simulate",
      command: "./simulate.sh demo",
      proto: "MQTT",
      ports: "1883/TCP",
      means:
        "The calm scenario — a home under watch with one genuine finding. It peaks at YELLOW by design and never reaches RED.",
      caution:
        "A quiet GREEN stretch here is the script resting, not the feed having stopped.",
    },
  },
  {
    match: /Drill complete|Cycle complete/i,
    intel: {
      kind: "Drill control",
      tool: "risk engine",
      proto: "MQTT",
      means:
        "The sweep finished. Scores decay toward baseline and the next cycle opens from wherever the last one left off.",
      caution: "Decay is cosmetic pacing; the recorded alerts are unaffected.",
    },
  },

  // -- authority and detection nodes ---------------------------------------
  {
    match: /governance online/i,
    intel: {
      kind: "Node health",
      tool: "mosquitto + risk engine",
      proto: "MQTT",
      ports: "1883/TCP",
      means:
        "The Pi4 decision-maker is up: broker, scoring engine and dashboard, with the watchdog armed.",
      caution: "A health line says the process answered, not that its scoring is correct.",
    },
  },
  {
    match: /Detection node online/i,
    intel: {
      kind: "Detector health",
      tool: "Suricata",
      command: "suricata -i eth0 --af-packet",
      proto: "AF_PACKET",
      means:
        "Pi3a's signature engine is loaded and watching the mirrored LAN segment with no drops reported.",
      caution:
        "Only traffic the switch mirrors is visible here. Anything off-segment is invisible to this node.",
    },
  },
  {
    match: /heartbeat steady/i,
    intel: {
      kind: "Detector health",
      tool: "Suricata + systemd",
      proto: "MQTT",
      ports: "1883/TCP",
      means: "The detection node is still reporting on schedule with no packet loss.",
      caution: "A steady heartbeat is not evidence about the traffic it saw.",
    },
  },

  // -- ordinary household traffic -------------------------------------------
  {
    match: /IP camera checked in|stream healthy/i,
    intel: {
      kind: "LAN observation",
      tool: "ARP + DHCP fingerprint",
      proto: "RTSP / RTP",
      ports: "554/TCP",
      means:
        "A known camera announced itself and its stream is healthy. The identity comes from its MAC OUI and DHCP fingerprint, both of which the camera itself supplies.",
      caution:
        "A device can spoof its MAC, so 'known' means 'recognised', not 'trustworthy'.",
    },
  },
  {
    match: /plug reported in|plug load changed/i,
    intel: {
      kind: "LAN observation",
      tool: "MQTT telemetry (Tasmota-style)",
      proto: "MQTT",
      ports: "1883/TCP",
      means:
        "The smart plug published a power reading. The jump from standby to load is a resident switching something on.",
      caution:
        "Load is a proxy for activity, not for intent — a relay could also be driven remotely.",
    },
  },
  {
    match: /Door sensor paired|Front door opened|Front door closed/i,
    intel: {
      kind: "LAN observation",
      tool: "ESP32-C3 contact sensor",
      proto: "IEEE 802.11",
      means:
        "The door contact reported a state change over its wireless link, with the battery level included.",
      caution:
        "The sensor reports state; it cannot tell a resident from an intruder, or a replay from a press.",
    },
  },
  {
    match: /Unfamiliar device joined/i,
    intel: {
      kind: "LAN observation",
      tool: "ARP watch + DHCP fingerprint",
      proto: "ARP / DHCP",
      means:
        "A new MAC appeared on the monitored network and is being watched before it is trusted.",
      caution:
        "New is not hostile. Most join events are guests, phones and replacement hardware.",
    },
  },
  {
    match: /Unfamiliar device identified/i,
    intel: {
      kind: "LAN observation",
      tool: "DHCP fingerprint + OUI lookup",
      proto: "DHCP",
      means:
        "The unknown endpoint resolved to a household device on the guest network and was promoted to known.",
      caution:
        "Identification is a heuristic over self-reported fields; it can be fooled deliberately.",
    },
  },

  // -- reconnaissance -------------------------------------------------------
  {
    match: /nmap port scan/i,
    intel: {
      kind: "Reconnaissance",
      tool: "nmap",
      command:
        "nmap -sS -Pn -p 1-1024,554,8000,8443 --open 192.168.100.61",
      rule: "ET SCAN nmap -sS window 1024",
      sid: 2009582,
      proto: "TCP",
      ports: "1-1024, 554, 8000, 8443",
      mitre: "T1046 · Network Service Discovery",
      means:
        "A SYN sweep walked the camera's port range to inventory what it exposes. This is the step that comes before every exploit, and it costs the attacker almost nothing.",
      caution:
        "A scan is not a compromise. It is also indistinguishable from some management tooling, so it scores as intent rather than as access.",
    },
  },
  {
    match: /probed for default credentials/i,
    intel: {
      kind: "Reconnaissance",
      tool: "hydra",
      command:
        'hydra -l admin -P top-1000.txt 192.168.100.61 http-post-form "/cgi-bin/login:user=^USER^&pass=^PASS^:F=incorrect"',
      rule: "ET SCAN default credential probe",
      sid: 2010935,
      proto: "HTTP",
      ports: "80/TCP",
      mitre: "T1110.001 · Brute Force: Password Guessing",
      means:
        "Fourteen logins in thirty seconds against the camera's web interface from a host on the guest network — a wordlist run against the vendor default.",
      caution:
        "Volume alone proves the attempt, not the outcome. Whether a credential worked is a separate finding.",
    },
  },
  {
    match: /Probe rejected/i,
    intel: {
      kind: "Reconnaissance",
      tool: "Suricata (HTTP response inspection)",
      rule: "ET SCAN default credential probe",
      sid: 2010935,
      proto: "HTTP",
      ports: "80/TCP",
      mitre: "T1110.001 · Brute Force: Password Guessing",
      means:
        "Every attempt in the wordlist was refused. The camera is not configured with a vendor default, so this avenue closed.",
      caution:
        "Resistance to one wordlist is not resistance to all of them, and a slow spray defeats rate limits.",
    },
  },

  // -- exposure -------------------------------------------------------------
  {
    match: /firmware is stale/i,
    intel: {
      kind: "Exposure",
      tool: "LAN join watch + version probe",
      cve: "CVE-2021-36260 · CVE-2017-7921",
      proto: "HTTP",
      ports: "80/TCP",
      mitre: "T1190 · Exploit Public-Facing Application",
      means:
        "The device reports a fourteen-month-old firmware with unpatched remote flaws published against that family. The weakness is the age, not anything the device did.",
      caution:
        "Unpatched is a liability, not an incident. Most such devices are never attacked, and this finding would sit open indefinitely on its own.",
    },
  },
  {
    match: /fetched unsigned firmware/i,
    intel: {
      kind: "Integrity failure",
      tool: "LAN join watch + TLS/HTTP inspection",
      proto: "HTTP",
      ports: "80/TCP",
      mitre: "T1553 · Subvert Trust Controls",
      means:
        "A device pulled a firmware image over plain HTTP with no signature check. Whatever is in that image will now run with the device's privileges.",
      caution:
        "The image was not inspected — only the absence of a signature is proven. The content could be benign vendor tooling.",
    },
  },

  // -- compromise -----------------------------------------------------------
  {
    match: /beaconing to an unknown host/i,
    intel: {
      kind: "Command and control",
      tool: "Suricata + TLS fingerprinting",
      rule: "ET TROJAN Possible C2 Beacon (POST)",
      sid: 2027751,
      proto: "TLS / HTTPS",
      ports: "8443/TCP",
      mitre: "T1071.001 · Application Layer Protocol: Web Protocols",
      means:
        "The camera contacts the same external host on a fixed jittered schedule with near-identical small uploads — the shape of a check-in, not of a person using a camera.",
      caution:
        "Beacon cadence is behavioural evidence. It can also be a vendor telemetry endpoint or a badly built NTP client.",
    },
  },
  {
    match: /exploit attempt succeeded/i,
    intel: {
      kind: "Compromise",
      tool: "Suricata + manual request replay",
      rule: "ET EXPLOIT Hikvision IP Camera Command Injection",
      sid: 2017956,
      cve: "CVE-2021-36260",
      proto: "HTTP",
      ports: "80/TCP",
      mitre: "T1190 · Exploit Public-Facing Application",
      means:
        "One crafted request in a series returned a success response carrying a shell banner instead of an error. That is a command reaching the device, not merely a malformed packet.",
      caution:
        "A shell banner shows a command executed. It does not, on its own, show what was run or whether anything was read.",
    },
  },
  {
    match: /Lateral movement/i,
    intel: {
      kind: "Lateral movement",
      tool: "hydra",
      command:
        "hydra -l root -P rockyou.txt ssh://192.168.100.2 -t 4 -f",
      rule: "ET SCAN SSH Brute Force from IoC Host",
      sid: 2001219,
      proto: "SSH",
      ports: "22/TCP",
      mitre: "T1021.004 · Remote Services: SSH",
      means:
        "The compromised camera turned on the governance node — 240 SSH authentications in forty seconds. An embedded device has no reason to speak SSH to a server.",
      caution:
        "The nftables rule dropped these on the third retry, so the important question is what is still allowed through, not what was blocked.",
    },
  },
  {
    match: /Credential harvest attempt/i,
    intel: {
      kind: "Impact",
      tool: "filesystem audit (inotify)",
      cve: "CVE-2021-36260",
      proto: "SSH",
      ports: "22/TCP",
      mitre: "T1003.008 · OS Credential Dumping: /etc/passwd and /etc/shadow",
      means:
        "The camera's session reached for the password database and for the SSH authorised-keys file. Those two files together are how an intruder converts brief access into permanent access.",
      caution:
        "Both writes were denied by the read-only API surface. Denied attempts still prove the intent and the capability.",
    },
  },

  // -- response -------------------------------------------------------------
  {
    match: /Containment|quarantined/i,
    intel: {
      kind: "Response",
      tool: "Pi4 governance (nftables + VLAN move)",
      proto: "802.1Q / DNS",
      mitre: "T1562.001 mitigation · response action",
      means:
        "The camera was moved to the quarantine VLAN, its DNS sinkholed and its stream credentials revoked. The lateral path into the governance node is closed.",
      caution:
        "Containment stops the spread; it does not establish how the device was reached in the first place. That question stays open.",
    },
  },

  // -- indicator ------------------------------------------------------------
  {
    match: /Indicator reading YELLOW/i,
    intel: {
      kind: "Indicator",
      tool: "ESP32-C3 OLED",
      proto: "MQTT",
      ports: "1883/TCP",
      means:
        "The physical indicator mirrors the risk band for anyone standing at the rig rather than at the dashboard. YELLOW is advisory.",
      caution: "YELLOW never sends a notification and needs no operator action.",
    },
  },
  {
    match: /Indicator reading RED/i,
    intel: {
      kind: "Indicator",
      tool: "ESP32-C3 OLED + LED",
      proto: "MQTT",
      ports: "1883/TCP",
      means:
        "RED is mirrored to the OLED and the LED, and it is the first band that wakes someone up by email.",
      caution:
        "An indicator shows the band, not its cause. Always read the alert behind it.",
    },
  },
  {
    match: /Indicator reading GREEN/i,
    intel: {
      kind: "Indicator",
      tool: "ESP32-C3 OLED + LED",
      proto: "MQTT",
      ports: "1883/TCP",
      means: "The indicator has returned to steady GREEN and the incident is closed.",
      caution: "GREEN means the score decayed, not that the weakness was remediated.",
    },
  },

  // -- wrap ----------------------------------------------------------------
  {
    match: /All endpoints nominal/i,
    intel: {
      kind: "Summary",
      tool: "risk engine",
      proto: "MQTT",
      means:
        "Node health, open findings and quarantine state rolled into one line at the end of a sweep.",
      caution:
        "Nominal is a statement about the monitored mesh at that moment, nothing more.",
    },
  },
];

/** The curated intel for an alert title, or null when nothing matches. */
export function eventIntel(title: string): EventIntel | null {
  for (const { match, intel } of RULES) {
    if (match.test(title)) return intel;
  }
  return null;
}

/** The rows the floating box renders, in order, skipping empty fields. */
export function intelRows(intel: EventIntel): Array<[string, string]> {
  const rows: Array<[string, string]> = [
    ["tool", intel.tool],
    ["command", intel.command],
    ["rule", intel.rule],
    ["sid", intel.sid === undefined ? undefined : String(intel.sid)],
    ["proto", intel.proto],
    ["ports", intel.ports],
    ["cve", intel.cve],
    ["mitre", intel.mitre],
  ].filter(([, v]) => Boolean(v)) as Array<[string, string]>;
  return rows;
}
