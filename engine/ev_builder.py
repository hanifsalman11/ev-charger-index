import os
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ==========================================
# ENVIRONMENT CONFIGURATION
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://hanifsalman11.github.io/ev-charger-index").rstrip("/")
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6").strip()
CUSTOM_EV = os.environ.get("CUSTOM_EV", "").strip()
PAGES_PER_RUN = int(os.environ.get("PAGES_PER_RUN", "3"))

DOCS_DIR = "docs"
DATA_DIR = "data"
PUBLISHED_FILE = os.path.join(DATA_DIR, "published_evs.json")
MONETIZATION_FILE = os.path.join(DATA_DIR, "monetization.json")

# Format: (Vehicle Name, Usable Battery kWh, Max AC Onboard Charger kW, Max AC Amps, Native Port, Efficiency mi/kWh)
SEED_EVS = [
    ("Tesla Model Y Long Range AWD", 78.1, 11.5, 48, "NACS (SAE J3400)", 3.5),
    ("Ford F-150 Lightning Extended Range", 131.0, 19.2, 80, "J1772 / NACS", 2.1),
    ("Rivian R1S Dual-Motor Max Pack", 141.0, 11.5, 48, "J1772 / NACS", 2.3),
    ("Hyundai Ioniq 5 AWD Long Range", 77.4, 11.5, 48, "J1772 / NACS", 3.4),
    ("Chevrolet Equinox EV 2LT", 85.0, 11.5, 48, "J1772 / NACS", 3.3),
    ("Kia EV9 Land AWD Three-Row", 99.8, 10.9, 48, "J1772 / NACS", 2.6),
    ("Tesla Model 3 Highland Long Range", 78.1, 11.5, 48, "NACS (SAE J3400)", 4.0),
    ("Tesla Cybertruck All-Wheel Drive", 123.0, 11.5, 48, "NACS (SAE J3400)", 2.4),
    ("Ford Mustang Mach-E Premium ER", 91.0, 10.5, 48, "J1772 / NACS", 3.1),
    ("Cadillac Lyriq Luxury AWD", 102.0, 19.2, 80, "J1772 / NACS", 2.9),
    ("Honda Prologue Touring AWD", 85.0, 11.5, 48, "J1772", 3.0),
    ("BMW i4 eDrive40 Gran Coupe", 81.5, 11.0, 48, "J1772", 3.6),
    ("Porsche Macan Electric 4", 95.0, 11.0, 48, "J1772 / NACS", 3.1),
    ("Rivian R1T Dual-Motor Large Pack", 109.0, 11.5, 48, "J1772 / NACS", 2.2),
    ("Chevrolet Silverado EV RST Max Range", 205.0, 19.2, 80, "J1772 / NACS", 1.9),
    ("Hyundai Ioniq 6 SE Long Range", 77.4, 11.5, 48, "J1772 / NACS", 4.1),
    ("Kia EV6 Wind AWD", 77.4, 10.9, 48, "J1772 / NACS", 3.4),
    ("Volkswagen ID.4 Pro S", 77.0, 11.0, 48, "J1772", 3.3),
    ("Volvo EX30 Twin Motor Performance", 64.0, 11.0, 48, "J1772 / NACS", 3.3),
    ("Volvo EX90 Twin Motor AWD", 107.0, 11.0, 48, "NACS / J1772", 2.6),
    ("Polestar 3 Long Range Dual Motor", 107.0, 11.0, 48, "NACS / J1772", 2.7),
    ("Lucid Air Pure Rear-Wheel Drive", 84.0, 19.2, 80, "NACS / J1772", 4.4),
    ("Audi Q6 e-tron Quattro", 94.9, 11.0, 48, "J1772", 3.1),
    ("Jeep Wagoneer S Launch Edition", 100.5, 11.5, 48, "J1772", 2.9),
    ("Toyota RAV4 Prime Plug-In Hybrid", 18.1, 6.6, 32, "J1772", 2.8),
    ("Jeep Wrangler 4xe Plug-In Hybrid", 17.3, 7.2, 32, "J1772", 1.8),
    ("Chevrolet Blazer EV RS AWD", 85.0, 11.5, 48, "J1772", 3.0),
    ("Nissan Ariya Evolve+ e-4ORCE", 87.0, 7.2, 32, "J1772 / NACS", 3.0),
    ("Subaru Solterra Limited AWD", 72.8, 6.6, 32, "J1772", 3.1),
    ("GMC Hummer EV Pickup 3X", 212.7, 19.2, 80, "J1772 / NACS", 1.6)
]


def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Could not parse {filepath}: {e}")
    return default


def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    return re.sub(r"[\s-]+", "-", text).strip("-")


def safe_float(val, default=77.4):
    try:
        cleaned = re.sub(r"[^0-9.]", "", str(val))
        return float(cleaned) if cleaned else float(default)
    except Exception:
        return float(default)


def build_amazon_url(search_keywords, mon_cfg):
    domain = mon_cfg.get("marketplace_domain", "www.amazon.com")
    tag = mon_cfg.get("amazon_associate_tag", "YOUR_AMAZON_TAG-20")
    encoded_q = urllib.parse.quote_plus(search_keywords)
    return f"https://{domain}/s?k={encoded_q}&tag={tag}"


def discover_google_ev_queries():
    """Mengambil model EV yang sedang banyak dicari kalkulator charger-nya di Google Autocomplete US."""
    discovered = []
    seeds = [
        "level 2 charger for ",
        "home charger wire size for ",
        "charging time calculator for "
    ]
    for seed in seeds:
        try:
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q={urllib.parse.quote(seed)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for suggestion in data[1]:
                    cleaned = suggestion.lower()
                    for pref in seeds:
                        cleaned = cleaned.replace(pref, "")
                    cleaned = re.sub(r"\b(level 2|charger|charging|time|calculator|home|wire|size|install)\b", "", cleaned).strip()
                    if 4 <= len(cleaned) <= 38:
                        discovered.append((cleaned.title(), 82.0, 11.5, 48, "J1772 / NACS", 3.2))
        except Exception as e:
            print(f"[WARN] Google Suggest notice: {e}")
    return discovered


def build_deterministic_ev_data(ev_tuple):
    """Mesin Fisika Baterai & Standar Kelistrikan NEC Article 625 (100% bebas gagal)."""
    ev_name, batt_kwh, max_kw, max_amps, port_type, eff_mi = ev_tuple

    # NEC Article 625 Rule: Circuit breaker must be rated at 125% of continuous EVSE load
    if max_amps >= 80:
        rec_breaker = 100
        wire_awg = "3 AWG Copper THHN in Conduit (or 2 AWG Copper)"
        evse_title = "80-Amp 19.2kW Hardwired Level 2 Commercial/Home EV Charger"
        evse_query = "80 Amp 19.2kW Level 2 EV Charger Hardwired"
        evse_price = "$699 - $1,199"
    elif max_amps >= 48:
        rec_breaker = 60
        wire_awg = "6 AWG Copper THHN in Conduit (or 4 AWG NM-B Romex)"
        evse_title = "48-Amp 11.5kW Hardwired / NEMA 14-50 Smart Level 2 EV Charger"
        evse_query = "48 Amp Level 2 EV Charger Hardwired NEMA 14-50 UL Listed"
        evse_price = "$399 - $599"
    else:
        rec_breaker = 40
        wire_awg = "8 AWG Copper THHN / NM-B Wire"
        evse_title = "32-Amp / 40-Amp NEMA 14-50 Plug-In Level 2 Smart EV Charger"
        evse_query = "40 Amp NEMA 14-50 Level 2 Smart EV Charger"
        evse_price = "$279 - $449"

    # Waktu cas 20% ke 80% (60% dari kapasitas usable) dengan efisiensi onboard rectifier 92%
    energy_20_80_kwh = round(batt_kwh * 0.60, 1)
    hrs_20_80 = round(energy_20_80_kwh / (max_kw * 0.92), 1)
    miles_per_hr = round(max_kw * 0.92 * eff_mi, 1)

    return {
        "ev_name": ev_name,
        "seo_title": f"{ev_name} Home Charger Calculator: Amps, Wire Size & Charge Time (2026)",
        "meta_description": f"Calculate exact Level 2 charging time ({hrs_20_80} hrs for 20%–80%), NEC wire gauge ({wire_awg}), and circuit breaker size ({rec_breaker}A) for the {ev_name}.",
        "specs": {
            "usable_battery_kwh": batt_kwh,
            "max_ac_kw": max_kw,
            "max_ac_amps": max_amps,
            "recommended_breaker_amps": rec_breaker,
            "recommended_wire_awg": wire_awg,
            "native_port": port_type,
            "efficiency_mi_per_kwh": eff_mi
        },
        "electrical_verdict": f"The {ev_name} features a {batt_kwh} kWh usable battery pack and a {max_kw} kW ({max_amps}A continuous) onboard AC charger. Per NEC Article 625 (80% continuous load rule), running at full {max_amps}A speed requires a dedicated {rec_breaker}-Amp 240V 2-pole circuit wired with {wire_awg}, recharging from 20% to 80% in approximately {hrs_20_80} hours (+{miles_per_hr} miles of range per hour).",
        "hardware_bundle": [
            {
                "badge": "Matched Level 2 EVSE",
                "title": evse_title,
                "price_range": evse_price,
                "amazon_query": evse_query,
                "nec_note": f"Delivers up to {max_kw} kW at 240V with dynamic amperage dip-switches and Wi-Fi off-peak scheduling."
            },
            {
                "badge": "Industrial Anti-Melt Outlet",
                "title": "Hubbell HBL9450A / Bryant 9450FR Heavy-Duty Industrial NEMA 14-50R Receptacle",
                "price_range": "$54 - $89",
                "amazon_query": "Hubbell 9450A Bryant 9450FR Industrial NEMA 14-50 Outlet EV",
                "nec_note": "Standard $12 hardware-store dryer outlets melt under multi-hour 40A EV loads. Always use an industrial torque-rated receptacle."
            },
            {
                "badge": "NEC 625 Copper Conductor",
                "title": f"{wire_awg} 90°C Rated Building Wire (25ft – 100ft Cut)",
                "price_range": "$95 - $289",
                "amazon_query": "6 AWG THHN Copper Wire 6/3 Romex NM-B EV Charger",
                "nec_note": f"Sized for a {rec_breaker}A 240V circuit with under 3% voltage drop over standard residential garage conduit runs."
            },
            {
                "badge": "NACS / J1772 Fast Adapter",
                "title": "80-Amp 250V Heavy-Duty NACS (Tesla) to J1772 / J1772 to NACS Locking Adapter",
                "price_range": "$79 - $159",
                "amazon_query": "80A NACS to J1772 Tesla EV Charger Adapter UL Listed",
                "nec_note": f"Ensures universal cross-compatibility between your {ev_name} ({port_type}) and any Level 2 destination or home wall connector."
            }
        ],
        "installation_checklist": [
            f"Size your circuit breaker to 125% of continuous charger output (NEC 625.41): a {max_amps}A continuous charge requires a {rec_breaker}A 2-pole 240V breaker.",
            "Hardwire any EVSE operating at 48 Amps or higher; NEC guidelines and most EVSE manufacturers limit plug-in NEMA 14-50 installations to 40 Amps continuous (50A breaker).",
            "Torque all breaker, disconnect, and receptacle lugs to exact manufacturer inch-pound specifications (typically 75 in-lbs on Hubbell 9450A) using a calibrated torque screwdriver.",
            "When installing a NEMA 14-50 plug-in outlet in a garage or outdoors, NEC requires a GFCI-protected 2-pole circuit breaker in your main panel."
        ],
        "faqs": [
            {
                "q": f"How long does it take to charge a {ev_name} at home on Level 2?",
                "a": f"With a {batt_kwh} kWh usable battery and {max_kw} kW ({max_amps}A) onboard AC charger, a daily 20% to 80% top-up ({energy_20_80_kwh} kWh) takes approximately {hrs_20_80} hours, while a 0% to 100% full charge takes about {round(batt_kwh / (max_kw * 0.92), 1)} hours."
            },
            {
                "q": f"What size wire and breaker do I need for a {ev_name} home charger?",
                "a": f"To achieve the maximum {max_amps}A ({max_kw} kW) charging speed, install a hardwired EVSE on a {rec_breaker}A 2-pole 240V breaker using {wire_awg}. If using a NEMA 14-50 plug on a 50A breaker, set the charger to 40A continuous (9.6 kW)."
            },
            {
                "q": f"How much does it cost to charge a {ev_name} at home?",
                "a": f"At the US national average residential electricity rate of $0.16 per kWh, charging the {ev_name} from 20% to 80% ({energy_20_80_kwh} kWh plus ~8% charging loss) costs approximately ${round((energy_20_80_kwh / 0.92) * 0.16, 2)}, or ${round((batt_kwh / 0.92) * 0.16, 2)} for a complete 0%–100% charge."
            }
        ]
    }


def generate_ev_data(ev_tuple):
    """Memanggil Gemini 2.5 Flash API; jika gagal otomatis memakai Deterministic NEC Electrical Engine."""
    if not GEMINI_API_KEY:
        return build_deterministic_ev_data(ev_tuple)

    ev_name, batt_kwh, max_kw, max_amps, port_type, eff_mi = ev_tuple
    prompt = f"""
You are a Master Licensed Electrician (NEC Article 625 Specialist) & EV Charging Engineer. Create an accurate 2026 Level 2 home charger sizing, wire gauge, and charging time guide for: "{ev_name}".
Baseline reference specs: Usable Battery={batt_kwh} kWh, Max AC Charging={max_kw} kW ({max_amps}A), Port={port_type}, Efficiency={eff_mi} mi/kWh.
Return ONLY a valid JSON object matching this exact schema:
{{
  "ev_name": "{ev_name}",
  "seo_title": "{ev_name} Home Charger Calculator: Amps, Wire Size & Charge Time (2026)",
  "meta_description": "Calculate exact Level 2 charging time, NEC copper wire gauge (AWG), and circuit breaker size for the {ev_name}.",
  "specs": {{
    "usable_battery_kwh": {batt_kwh},
    "max_ac_kw": {max_kw},
    "max_ac_amps": {max_amps},
    "recommended_breaker_amps": 60,
    "recommended_wire_awg": "6 AWG Copper THHN",
    "native_port": "{port_type}",
    "efficiency_mi_per_kwh": {eff_mi}
  }},
  "electrical_verdict": "3-sentence technical summary stating usable battery kWh, max onboard AC kW/Amps, exact 20%-80% charge time, and required NEC breaker/wire size.",
  "hardware_bundle": [
    {{
      "badge": "Matched Level 2 EVSE",
      "title": "Exact 48A or 80A Smart Level 2 EV Charger recommendation",
      "price_range": "$399 - $599",
      "amazon_query": "48 Amp Level 2 Smart EV Charger UL Listed",
      "nec_note": "1-sentence NEC installation note"
    }},
    {{
      "badge": "Industrial NEMA 14-50 Outlet",
      "title": "Hubbell HBL9450A / Bryant 9450FR Heavy-Duty Industrial NEMA 14-50R Receptacle",
      "price_range": "$55 - $89",
      "amazon_query": "Hubbell HBL9450A Industrial NEMA 14-50 Outlet EV",
      "nec_note": "1-sentence thermal safety explanation"
    }},
    {{
      "badge": "NEC 625 Copper Conductor",
      "title": "6 AWG THHN Copper or 6/3 NM-B Building Wire",
      "price_range": "$110 - $260",
      "amazon_query": "6 AWG THHN Copper Wire EV Charger",
      "nec_note": "1-sentence ampacity and temperature rating note"
    }},
    {{
      "badge": "Heavy-Duty NACS/J1772 Adapter",
      "title": "80A 250V NACS to J1772 / J1772 to NACS Adapter",
      "price_range": "$79 - $159",
      "amazon_query": "80A NACS J1772 EV Charger Adapter",
      "nec_note": "1-sentence connector compatibility note"
    }}
  ],
  "installation_checklist": [
    "NEC 80% continuous load rule step",
    "Hardwired vs NEMA 14-50 plug step",
    "Terminal torque specification step",
    "GFCI breaker requirement step"
  ],
  "faqs": [
    {{"q": "How long does it take to charge a {ev_name} at home?", "a": "Exact hours for 20%-80% and 0%-100%."}},
    {{"q": "What size wire and breaker do I need for a {ev_name} charger?", "a": "Exact AWG copper wire and breaker size per NEC Article 625."}},
    {{"q": "How much does it cost to charge a {ev_name} at home?", "a": "Exact dollar cost at average US kWh rates."}}
  ]
}}
"""

    for model_id in ["gemini-2.5-flash", "gemini-2.0-flash"]:
        try:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json"
                }
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                raw_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)
                parsed = json.loads(raw_text)
                if "specs" in parsed and "hardware_bundle" in parsed:
                    return parsed
        except Exception as e:
            print(f"[WARN] Gemini ({model_id}) notice for '{ev_name}': {e}")

    return build_deterministic_ev_data(ev_tuple)


def build_ev_html_page(data, slug, mon_cfg):
    ev_name = data.get("ev_name", "Electric Vehicle")
    sp = data.get("specs", {})
    batt_kwh = round(safe_float(sp.get("usable_battery_kwh", 78.0), 78.0), 1)
    max_kw = round(safe_float(sp.get("max_ac_kw", 11.5), 11.5), 1)
    max_amps = int(safe_float(sp.get("max_ac_amps", 48), 48))
    rec_breaker = int(safe_float(sp.get("recommended_breaker_amps", 60), 60))
    wire_awg = sp.get("recommended_wire_awg", "6 AWG Copper THHN")
    port_type = sp.get("native_port", "NACS / J1772")
    eff_mi = round(safe_float(sp.get("efficiency_mi_per_kwh", 3.2), 3.2), 1)

    header_cta = mon_cfg.get("header_cta", {})
    header_cta_url = build_amazon_url(header_cta.get("search_query", "Level+2+EV+Charger+48+Amp"), mon_cfg)

    schema_graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "SoftwareApplication",
                "name": f"{ev_name} Home Charger & NEC Wire Gauge Calculator",
                "applicationCategory": "UtilitiesApplication",
                "operatingSystem": "Web Browser",
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f.get("q", ""),
                        "acceptedAnswer": {"@type": "Answer", "text": f.get("a", "")}
                    } for f in data.get("faqs", [])
                ]
            }
        ]
    }

    bundle_html = ""
    for item in data.get("hardware_bundle", []):
        amz_url = build_amazon_url(item.get("amazon_query", item.get("title", "Level 2 EV Charger")), mon_cfg)
        bundle_html += f"""
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between hover:border-teal-500/60 transition">
          <div>
            <div class="flex items-center justify-between gap-2 mb-2">
              <span class="text-xs font-bold uppercase tracking-wider bg-teal-500/10 text-teal-400 border border-teal-500/20 px-2.5 py-0.5 rounded">{item.get('badge', 'NEC Hardware')}</span>
              <span class="text-sm font-bold text-emerald-400">{item.get('price_range', '$99+')}</span>
            </div>
            <h3 class="text-base font-bold text-white mt-2">{item.get('title', '')}</h3>
            <p class="text-xs text-slate-400 mt-2 leading-relaxed">⚡ {item.get('nec_note', '')}</p>
          </div>
          <a href="{amz_url}" target="_blank" rel="nofollow sponsored" class="mt-5 block text-center bg-teal-500 hover:bg-teal-400 text-slate-950 font-extrabold py-2.5 px-4 rounded-lg text-sm transition shadow-lg">
            Check Price on Amazon →
          </a>
        </div>"""

    # Build Circuit Breaker Comparison Matrix
    breaker_tiers = [
        (20, 16, 3.8, "12 AWG Copper", "NEMA 6-20 / Hardwired"),
        (30, 24, 5.8, "10 AWG Copper", "NEMA 14-30 / Dryer Split"),
        (40, 32, 7.7, "8 AWG Copper", "NEMA 14-50 / Hardwired"),
        (50, 40, 9.6, "6 AWG Copper", "NEMA 14-50 Plug Max"),
        (60, 48, 11.5, "6 AWG THHN / 4 AWG NM-B", "Hardwired Wall Connector"),
        (100, 80, 19.2, "3 AWG Copper THHN", "Hardwired High-Output Pro")
    ]
    matrix_rows_html = ""
    energy_60pct = batt_kwh * 0.60
    for brk_a, cont_a, kw_out, awg_str, install_type in breaker_tiers:
        effective_kw = min(max_kw, kw_out)
        charge_hrs = round(energy_60pct / (effective_kw * 0.92), 1)
        mi_added = round(effective_kw * 0.92 * eff_mi, 1)
        capped_note = " (Onboard Cap)" if kw_out > max_kw else ""
        matrix_rows_html += f"""
        <tr class="border-b border-slate-800 hover:bg-slate-800/40">
          <td class="py-3 px-4 font-bold text-white">{brk_a}A Breaker</td>
          <td class="py-3 px-4 text-slate-300">{cont_a}A ({effective_kw} kW{capped_note})</td>
          <td class="py-3 px-4 font-bold text-teal-400">{awg_str}</td>
          <td class="py-3 px-4 font-bold text-emerald-400">{charge_hrs} hrs (+{mi_added} mi/hr)</td>
          <td class="py-3 px-4 text-xs text-slate-400">{install_type}</td>
        </tr>"""

    checklist_html = ""
    for idx, step_text in enumerate(data.get("installation_checklist", []), start=1):
        checklist_html += f"""
        <label class="flex items-start gap-3.5 bg-slate-900 border border-slate-800 rounded-xl p-4 cursor-pointer hover:border-slate-700 transition">
          <input type="checkbox" class="mt-1 w-5 h-5 accent-teal-500 rounded cursor-pointer nec-check">
          <span class="text-sm text-slate-200 leading-relaxed"><strong>NEC Step {idx}:</strong> {step_text}</span>
        </label>"""

    faqs_html = "".join([
        f"<div class='bg-slate-900 border border-slate-800 rounded-xl p-5'><h3 class='font-bold text-white text-base mb-2'>{f.get('q', '')}</h3><p class='text-sm text-slate-300 leading-relaxed'>{f.get('a', '')}</p></div>"
        for f in data.get("faqs", [])
    ])

    canonical_url = f"{SITE_BASE_URL}/{slug}.html"
    amz_domain = mon_cfg.get("marketplace_domain", "www.amazon.com")
    amz_tag = mon_cfg.get("amazon_associate_tag", "YOUR_AMAZON_TAG-20")

    html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{data.get('seo_title', ev_name)}</title>
  <meta name="description" content="{data.get('meta_description', '')}">
  <link rel="canonical" href="{canonical_url}">
  <meta property="og:title" content="{data.get('seo_title', ev_name)}">
  <meta property="og:description" content="{data.get('meta_description', '')}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical_url}">
  <script src="https://cdn.tailwindcss.com"></script>
  <script type="application/ld+json">{json.dumps(schema_graph)}</script>
</head>
<body class="bg-slate-950 text-slate-100 antialiased min-h-screen flex flex-col">
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-30">
    <div class="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
      <a href="index.html" class="text-lg font-black tracking-tight text-white flex items-center gap-2">
        <span class="bg-teal-500 text-slate-950 px-2 py-0.5 rounded font-black">EVSE</span>CalcIndex
      </a>
      <a href="{header_cta_url}" target="_blank" rel="nofollow sponsored" class="text-xs sm:text-sm bg-teal-500 hover:bg-teal-400 text-slate-950 font-extrabold px-3.5 py-2 rounded-lg transition">
        {header_cta.get('cta_text', 'Shop Level 2 EV Chargers →')}
      </a>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-4 py-10 flex-1 w-full">
    <div class="mb-8">
      <div class="flex flex-wrap items-center gap-2.5 mb-3">
        <span class="text-xs font-extrabold uppercase tracking-widest bg-teal-500 text-slate-950 px-3 py-1 rounded-full">{batt_kwh} kWh Battery</span>
        <span class="text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-3 py-1 rounded-full">Max AC: {max_kw} kW ({max_amps}A)</span>
        <span class="text-xs font-semibold bg-slate-800 text-slate-300 px-3 py-1 rounded-full">Port: {port_type} | NEC Breaker: {rec_breaker}A</span>
      </div>
      <h1 class="text-3xl sm:text-4xl font-black text-white leading-tight">{data.get('seo_title', ev_name)}</h1>
      <div class="mt-4 bg-slate-900 border-l-4 border-teal-500 p-4 rounded-r-xl text-sm text-slate-200 leading-relaxed">
        <strong>NEC Article 625 Engineering Summary:</strong> {data.get('electrical_verdict', '')}
      </div>
    </div>

    <!-- INTERACTIVE EV CHARGING TIME, BREAKER & WIRE GAUGE CALCULATOR -->
    <section class="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 mb-12 shadow-2xl">
      <h2 class="text-xl font-extrabold text-white mb-2">Interactive {ev_name} Charge Time & NEC Wire Calculator</h2>
      <p class="text-xs text-slate-400 mb-6">Adjust your circuit breaker amperage, target battery charge percentage, and conduit wire distance to compute exact charging duration, NEC wire gauge, and cost per charge.</p>

      <div class="grid md:grid-cols-2 gap-8 items-center">
        <div class="space-y-5">
          <div>
            <label for="breakerSelect" class="block text-sm font-medium text-slate-300 mb-1.5">240V Circuit Breaker Size (NEC 80% Continuous Load)</label>
            <select id="breakerSelect" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-teal-500">
              <option value="20">20A Breaker → 16A Continuous (3.8 kW)</option>
              <option value="30">30A Breaker → 24A Continuous (5.8 kW)</option>
              <option value="40">40A Breaker → 32A Continuous (7.7 kW)</option>
              <option value="50">50A Breaker → 40A Continuous (9.6 kW NEMA 14-50 Max)</option>
              <option value="60" selected>60A Breaker → 48A Continuous (11.5 kW Hardwired)</option>
              <option value="100">100A Breaker → 80A Continuous (19.2 kW Pro Hardwired)</option>
            </select>
          </div>

          <div>
            <div class="flex justify-between text-sm font-medium mb-1.5">
              <label for="socSlider" class="text-slate-300">Battery Energy Added (% of {batt_kwh} kWh Pack)</label>
              <span class="text-teal-400 font-bold">+<span id="socVal">60</span>% (20% → 80%)</span>
            </div>
            <input id="socSlider" type="range" min="10" max="100" step="5" value="60" class="w-full accent-teal-500 cursor-pointer">
          </div>

          <div>
            <div class="flex justify-between text-sm font-medium mb-1.5">
              <label for="runSlider" class="text-slate-300">Panel-to-Charger Conduit Wire Run (Feet)</label>
              <span class="text-teal-400 font-bold"><span id="runVal">40</span> ft</span>
            </div>
            <input id="runSlider" type="range" min="10" max="150" step="10" value="40" class="w-full accent-teal-500 cursor-pointer">
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="bg-slate-950 border border-teal-500/30 rounded-xl p-4">
            <span class="text-xs uppercase text-teal-400 font-bold">Estimated Charge Time</span>
            <div class="text-2xl sm:text-3xl font-black text-white mt-1"><span id="timeOut">0.0</span> <span class="text-sm font-normal text-slate-400">hrs</span></div>
            <p id="speedNoteOut" class="text-xs text-slate-400 mt-1">At 11.5 kW (+36 mi/hr)</p>
          </div>

          <div class="bg-slate-950 border border-emerald-500/30 rounded-xl p-4">
            <span class="text-xs uppercase text-emerald-400 font-bold">NEC Copper Wire Gauge</span>
            <div id="awgOut" class="text-xl sm:text-2xl font-black text-emerald-400 mt-1">6 AWG Copper</div>
            <p id="costOut" class="text-xs text-slate-400 mt-1">Est. Session Cost: $8.15</p>
          </div>
        </div>
      </div>

      <div class="mt-6 bg-teal-950/40 border border-teal-500/30 rounded-xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div id="necAdviceBanner" class="text-sm text-teal-100 font-medium"></div>
        <a id="dynamicEvseBtn" href="{header_cta_url}" target="_blank" rel="nofollow sponsored" class="shrink-0 bg-teal-500 hover:bg-teal-400 text-slate-950 font-extrabold px-4 py-2.5 rounded-lg text-xs uppercase tracking-wider transition">
          Shop Matched EV Charger on Amazon →
        </a>
      </div>
    </section>

    <!-- 4-CARD HARDWARE BUNDLE -->
    <section class="mb-12">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-2xl font-extrabold text-white">Complete {ev_name} Home Charging Hardware Kit</h2>
        <span class="text-xs text-slate-400">UL-Listed & NEC Article 625 Compliant</span>
      </div>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">{bundle_html}</div>
    </section>

    <!-- CIRCUIT BREAKER & WIRE MATRIX TABLE -->
    <section class="mb-12">
      <h2 class="text-2xl font-extrabold text-white mb-4">{ev_name} Breaker Size, AWG Wire & Speed Matrix (20%–80% Charge)</h2>
      <div class="overflow-x-auto bg-slate-900 border border-slate-800 rounded-xl">
        <table class="w-full text-left border-collapse text-sm">
          <thead>
            <tr class="border-b border-slate-800 bg-slate-950/60 text-slate-400 uppercase text-xs">
              <th class="py-3.5 px-4">240V Breaker</th>
              <th class="py-3.5 px-4">Continuous Output</th>
              <th class="py-3.5 px-4 text-teal-400">Minimum Copper Wire</th>
              <th class="py-3.5 px-4 text-emerald-400">20%–80% Charge Time</th>
              <th class="py-3.5 px-4">Connection Type</th>
            </tr>
          </thead>
          <tbody>{matrix_rows_html}</tbody>
        </table>
      </div>
    </section>

    <!-- NEC INSTALLATION CHECKLIST -->
    <section class="mb-12">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-2xl font-extrabold text-white">Master Electrician NEC 625 Installation Checklist</h2>
        <span id="necBadge" class="text-xs font-bold bg-slate-800 text-teal-400 px-3 py-1 rounded-full">0 / 4 Completed</span>
      </div>
      <div class="space-y-3">{checklist_html}</div>
    </section>

    <!-- FAQ -->
    <section class="mb-12">
      <h2 class="text-2xl font-extrabold text-white mb-5">Frequently Asked Questions ({ev_name})</h2>
      <div class="space-y-4">{faqs_html}</div>
    </section>
  </main>

  <footer class="border-t border-slate-800 py-8 text-center text-xs text-slate-500 px-4">
    <p>© {datetime.now(timezone.utc).year} EVSECalcIndex. Independent EV Charging & NEC Electrical Sizing Database. As an Amazon Associate, we earn from qualifying purchases.</p>
  </footer>

  <script>
    const battKwh = {batt_kwh};
    const vehicleMaxKw = {max_kw};
    const effMi = {eff_mi};
    const amzDomain = "{amz_domain}";
    const amzTag = "{amz_tag}";

    const breakerSelect = document.getElementById('breakerSelect');
    const socSlider = document.getElementById('socSlider');
    const runSlider = document.getElementById('runSlider');
    const socVal = document.getElementById('socVal');
    const runVal = document.getElementById('runVal');
    const timeOut = document.getElementById('timeOut');
    const speedNoteOut = document.getElementById('speedNoteOut');
    const awgOut = document.getElementById('awgOut');
    const costOut = document.getElementById('costOut');
    const necAdviceBanner = document.getElementById('necAdviceBanner');
    const dynamicEvseBtn = document.getElementById('dynamicEvseBtn');

    function recalculateEv() {{
      const breakerA = parseInt(breakerSelect.value, 10);
      const socPct = parseInt(socSlider.value, 10);
      const runFt = parseInt(runSlider.value, 10);

      socVal.textContent = socPct;
      runVal.textContent = runFt;

      const contAmps = Math.round(breakerA * 0.80);
      const circuitKw = (contAmps * 240.0) / 1000.0;
      const actualKw = Math.min(vehicleMaxKw, circuitKw);
      const deliveredKw = actualKw * 0.92;

      const kwhNeeded = battKwh * (socPct / 100.0);
      const hours = kwhNeeded / deliveredKw;
      const milesPerHr = Math.round(deliveredKw * effMi);
      const wallKwh = kwhNeeded / 0.92;
      const sessionCost = wallKwh * 0.16;

      timeOut.textContent = hours.toFixed(1);
      speedNoteOut.textContent = `At ${{actualKw.toFixed(1)}} kW (+${{milesPerHr}} mi/hr)`;
      costOut.textContent = `Est. Cost (@$0.16/kWh): $${{sessionCost.toFixed(2)}}`;

      let wireLabel = "6 AWG Copper THHN";
      if (breakerA <= 20) wireLabel = runFt > 100 ? "10 AWG Copper" : "12 AWG Copper";
      else if (breakerA <= 30) wireLabel = runFt > 100 ? "8 AWG Copper" : "10 AWG Copper";
      else if (breakerA <= 40) wireLabel = runFt > 100 ? "6 AWG Copper" : "8 AWG Copper";
      else if (breakerA <= 50) wireLabel = runFt > 100 ? "4 AWG Copper" : "6 AWG Copper";
      else if (breakerA <= 60) wireLabel = runFt > 100 ? "4 AWG Copper THHN" : "6 AWG Copper THHN";
      else wireLabel = runFt > 90 ? "2 AWG Copper THHN" : "3 AWG Copper THHN";

      awgOut.textContent = wireLabel;

      const searchQuery = contAmps >= 48
        ? "48+Amp+Level+2+Smart+EV+Charger+Hardwired+UL+Listed"
        : `${{contAmps}}+Amp+NEMA+14-50+Level+2+Smart+EV+Charger`;

      necAdviceBanner.innerHTML = `⚡ <strong>NEC 625 Spec:</strong> A <strong>${{breakerA}}A breaker</strong> delivers <strong>${{contAmps}}A continuous (${{circuitKw.toFixed(1)}} kW)</strong> and requires <strong>${{wireLabel}}</strong> for a ${{runFt}} ft conduit run.`;
      dynamicEvseBtn.href = `https://${{amzDomain}}/s?k=${{searchQuery}}&tag=${{amzTag}}`;
    }}

    breakerSelect.addEventListener('change', recalculateEv);
    socSlider.addEventListener('input', recalculateEv);
    runSlider.addEventListener('input', recalculateEv);
    recalculateEv();

    const checks = document.querySelectorAll('.nec-check');
    const badge = document.getElementById('necBadge');
    checks.forEach(ch => {{
      ch.addEventListener('change', () => {{
        const done = Array.from(checks).filter(c => c.checked).length;
        badge.textContent = `${{done}} / ${{checks.length}} Completed`;
      }});
    }});
  </script>
</body>
</html>"""

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(html)


def rebuild_portal_sitemap_and_rss(published, mon_cfg):
    header_cta = mon_cfg.get("header_cta", {})
    header_cta_url = build_amazon_url(header_cta.get("search_query", "Level+2+EV+Charger+48+Amp"), mon_cfg)

    cards_html = ""
    for item in reversed(published):
        cards_html += f"""
        <a href="{item['slug']}.html" class="block bg-slate-900 border border-slate-800 hover:border-teal-500/60 rounded-xl p-5 transition group">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-black uppercase bg-teal-500 text-slate-950 px-2.5 py-0.5 rounded">{item.get('battery_kwh', 78)} kWh | {item.get('max_kw', 11.5)} kW AC</span>
            <span class="text-xs text-slate-400">{item.get('breaker_amps', 60)}A Breaker</span>
          </div>
          <h2 class="text-base font-bold text-white group-hover:text-teal-400 transition">{item['ev_name']} Home Charger & Wire Calculator</h2>
          <p class="text-xs text-slate-400 mt-2 line-clamp-2">{item['description']}</p>
          <span class="inline-block mt-4 text-xs font-extrabold text-teal-400">Calculate Charge Time & Wire Gauge →</span>
        </a>"""

    index_html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EVSECalcIndex — Level 2 EV Home Charger, NEC Wire Gauge & Charge Time Calculator (2026)</title>
  <meta name="description" content="Calculate exact Level 2 charging times, NEC Article 625 copper wire gauge (AWG), and 240V circuit breaker sizes for Tesla, Ford, Rivian, Hyundai, Kia, and Chevy EVs.">
  <link rel="canonical" href="{SITE_BASE_URL}/">
  <link rel="alternate" type="application/rss+xml" title="EVSECalcIndex RSS Feed" href="{SITE_BASE_URL}/rss.xml">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col">
  <header class="border-b border-slate-800 bg-slate-900/80 sticky top-0 z-30 backdrop-blur">
    <div class="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
      <div class="text-lg font-black text-white flex items-center gap-2">
        <span class="bg-teal-500 text-slate-950 px-2 py-0.5 rounded font-black">EVSE</span>CalcIndex
      </div>
      <a href="{header_cta_url}" target="_blank" rel="nofollow sponsored" class="text-xs sm:text-sm bg-teal-500 hover:bg-teal-400 text-slate-950 font-extrabold px-3.5 py-2 rounded-lg transition">
        {header_cta.get('cta_text', 'Shop Level 2 EV Chargers →')}
      </a>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-4 py-12 flex-1 w-full">
    <div class="text-center max-w-2xl mx-auto mb-10">
      <h1 class="text-3xl sm:text-5xl font-black text-white tracking-tight">EV Home Charger, Breaker & Wire Sizing Database</h1>
      <p class="text-slate-400 mt-3 text-base sm:text-lg">Select your electric vehicle or plug-in hybrid below to calculate exact Level 2 charging time (20%–80%), NEC copper wire gauge (AWG), and 240V breaker requirements.</p>
      <div class="mt-6">
        <input id="filterInput" type="text" placeholder="Search EV model (e.g. Tesla Model Y, F-150 Lightning, Rivian R1S, Ioniq 5, Equinox EV...)" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3.5 text-sm text-white focus:outline-none focus:border-teal-500">
      </div>
    </div>

    <div id="evGrid" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">{cards_html}</div>
  </main>

  <footer class="border-t border-slate-800 py-8 text-center text-xs text-slate-500">
    <p>© {datetime.now(timezone.utc).year} EVSECalcIndex. As an Amazon Associate, we earn from qualifying purchases.</p>
  </footer>

  <script>
    const filterInput = document.getElementById('filterInput');
    const cards = Array.from(document.getElementById('evGrid').children);
    filterInput.addEventListener('input', (e) => {{
      const q = e.target.value.toLowerCase();
      cards.forEach(c => {{
        c.style.display = c.textContent.toLowerCase().includes(q) ? 'block' : 'none';
      }});
    }});
  </script>
</body>
</html>"""

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls_xml = f"""  <url>
    <loc>{SITE_BASE_URL}/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>\n"""

    for item in published:
        urls_xml += f"""  <url>
    <loc>{SITE_BASE_URL}/{item['slug']}.html</loc>
    <lastmod>{item.get('date', today)}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.9</priority>
  </url>\n"""

    with open(os.path.join(DOCS_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls_xml}</urlset>""")

    rss_items = ""
    for item in list(reversed(published))[:30]:
        rss_items += f"""    <item>
      <title>{item['title']}</title>
      <link>{SITE_BASE_URL}/{item['slug']}.html</link>
      <guid>{SITE_BASE_URL}/{item['slug']}.html</guid>
      <description>{item['description']}</description>
    </item>\n"""

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>EVSECalcIndex EV Home Charger & NEC Wire Database</title>
    <link>{SITE_BASE_URL}/</link>
    <description>Interactive Level 2 EV Charger Amperage, Wire Gauge & Charging Time Calculators</description>
    <atom:link href="{SITE_BASE_URL}/rss.xml" rel="self" type="application/rss+xml" />
    <atom:link href="https://pubsubhubbub.appspot.com/" rel="hub" />
{rss_items}  </channel>
</rss>"""

    with open(os.path.join(DOCS_DIR, "rss.xml"), "w", encoding="utf-8") as f:
        f.write(rss_xml)

    with open(os.path.join(DOCS_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE_URL}/sitemap.xml\n")

    with open(os.path.join(DOCS_DIR, f"{INDEXNOW_KEY}.txt"), "w", encoding="utf-8") as f:
        f.write(INDEXNOW_KEY)


def notify_search_engines(new_urls):
    if not SITE_BASE_URL or not new_urls:
        return
    parsed_host = urllib.parse.urlparse(SITE_BASE_URL).netloc
    payload = {
        "host": parsed_host,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_BASE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": new_urls
    }
    try:
        req = urllib.request.Request(
            "https://api.indexnow.org/indexnow",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[INDEXNOW] Pushed {len(new_urls)} URLs (HTTP {resp.status})")
    except Exception as e:
        print(f"[WARN] IndexNow ping notice: {e}")

    try:
        hub_data = urllib.parse.urlencode({
            "hub.mode": "publish",
            "hub.url": f"{SITE_BASE_URL}/rss.xml"
        }).encode("utf-8")
        req_hub = urllib.request.Request(
            "https://pubsubhubbub.appspot.com/",
            data=hub_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        with urllib.request.urlopen(req_hub, timeout=15) as resp_hub:
            print(f"[WEBSUB] Google PubSubHubbub ping status: {resp_hub.status}")
    except Exception as e:
        print(f"[WARN] WebSub ping notice: {e}")


def main():
    published = load_json(PUBLISHED_FILE, [])
    mon_cfg = load_json(MONETIZATION_FILE, {})
    published_slugs = {item["slug"] for item in published}

    candidates = []
    if CUSTOM_EV:
        candidates.append((CUSTOM_EV.strip(), 82.0, 11.5, 48, "NACS / J1772", 3.2))
    candidates.extend(SEED_EVS)
    candidates.extend(discover_google_ev_queries())

    new_urls = []
    count = 0

    for ev_tuple in candidates:
        if count >= PAGES_PER_RUN:
            break
        ev_name = ev_tuple[0]
        slug = slugify(f"{ev_name}-home-charger-wire-size-calculator")
        if slug in published_slugs:
            continue

        print(f"[ENGINE] Generating EV charger & NEC wire calculator for: {ev_name}...")
        try:
            data = generate_ev_data(ev_tuple)
            build_ev_html_page(data, slug, mon_cfg)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sp = data.get("specs", {})

            published.append({
                "ev_name": data.get("ev_name", ev_name),
                "slug": slug,
                "title": data.get("seo_title", f"{ev_name} Home Charger Calculator"),
                "description": data.get("meta_description", ""),
                "battery_kwh": round(safe_float(sp.get("usable_battery_kwh", ev_tuple[1]), ev_tuple[1]), 1),
                "max_kw": round(safe_float(sp.get("max_ac_kw", ev_tuple[2]), ev_tuple[2]), 1),
                "breaker_amps": int(safe_float(sp.get("recommended_breaker_amps", 60), 60)),
                "date": today
            })
            published_slugs.add(slug)
            if SITE_BASE_URL:
                new_urls.append(f"{SITE_BASE_URL}/{slug}.html")
            count += 1
            time.sleep(2)
        except Exception as e:
            print(f"[ERROR] Failed building {ev_name}: {e}")

    save_json(PUBLISHED_FILE, published)
    rebuild_portal_sitemap_and_rss(published, mon_cfg)
    if new_urls and SITE_BASE_URL:
        new_urls.append(f"{SITE_BASE_URL}/")
        notify_search_engines(new_urls)
    print(f"[DONE] Published {count} new EV home charger calculator pages.")


if __name__ == "__main__":
    main()
