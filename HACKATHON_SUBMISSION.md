# 🏛️ JanSeva AI — Official Hackathon Submission Pack

This document contains everything needed to complete the hackathon submission form shown in your screenshots, record your 5-minute demo video, and present your 7-slide pitch deck.

---

## 📋 Copy-Paste Form Fields for Submission

### 1. Project name *
```text
JanSeva AI: Autonomous Zero-PII Public Service & Bureaucracy Execution Agent
```

---

### 2. Problem Statement *
```text
India has digitized hundreds of public services across 500+ fragmented central and state portals (such as MoRTH Parivahan Sarathi, the National Scholarship Portal, and state welfare portals). However, navigating them remains hostile for over 800 million citizens, particularly rural residents, students, and senior citizens.

Key challenges include:
1. Massive Bureaucratic Red Tape: Applying for a routine service requires navigating multi-step wizard forms, strict cascading dropdowns, complex eligibility rules, and strict file format/size constraints (e.g., PDFs under 200 KB).
2. The Cyber-Café Privacy Dilemma: Because citizens cannot easily complete these portals themselves, millions routinely hand over original Aadhaar cards, PAN cards, phone numbers, and OTPs to unregulated local cyber cafés, leading to widespread identity theft, document tampering, and financial fraud.
3. Lack of Accessibility & Guidance: Cryptic portal validation errors and multi-departmental redirects cause countless deserving students and low-income citizens to forfeit legitimate government welfare, subsidies, and educational scholarships.
```

---

### 3. Solution Description *
```text
JanSeva AI is a privacy-first autonomous web co-pilot that acts as a citizen's personal digital assistant for public service delivery. Rather than requiring users to struggle through confusing portal wizards or give away their identity, JanSeva AI allows citizens to state their goal in plain language or upload their documents, and autonomously navigates and executes the application on their desktop in slow-mo.

Core Capabilities & Agentic Architecture:
1. Zero-PII Local Confidential Vault: Sensitive citizen identity numbers (Aadhaar, DL, DOB, Income) are parsed locally and redacted into synthetic tokens (e.g., {{CITIZEN_AADHAAR_TOKEN}}) before cloud model processing. Real PII never leaks to external LLM APIs.
2. Multimodal Document Intake: Citizens can upload any marksheet, identity card, or government notice. A local entity extractor identifies and verifies citizen attributes directly into the local vault.
3. Dynamic DOM Perception & Universal Form Agent: Powered by Google Gemini reasoning and a Playwright actuator, the agent inspects live webpage forms, discovers field semantics via ARIA labels and placeholders, and executes form filling dynamically across arbitrary public portals.
4. Silent Mode Human-in-the-Loop Contract: Whenever an untrusted security boundary or human verification step is reached (visual CAPTCHAs, SMS OTPs, or statutory applicant declarations), the agent pauses in Silent Mode on the open desktop browser window, allowing the citizen to safely verify and submit.
5. Deterministic Rule Engine & Verifier: Integrates statutory rule evaluation (e.g., Motor Vehicles Act Form 1A medical fitness age exemptions, Central Sector Scheme academic merit percentiles) and generates cryptographic, auditable execution receipts with unique reference IDs.
```

---

### 4. Live prototype link *
```text
http://127.0.0.1:8001/
```
*(Public Tunnel / Deployed Prototype URL: `https://puny-ends-allow.loca.lt`)*

---

### 5. Public GitHub *
```text
https://github.com/Garv25667/autonomous-public-service-agent
```

---

### 6. Presentation / pitch deck link *
```text
http://127.0.0.1:8001/presentation
```
*(You can also export this 7-slide deck to PDF directly via the 🖨️ Export PDF button on the page)*

---

### 7. Demo video link *
*(Paste your YouTube or Google Drive video link after recording following the 5-minute script below)*

---

## 🎬 5-Minute Video Recording Walkthrough Script

Use this exact structure to record a smooth, high-scoring demo video:

| Timestamp | Section | What to Show on Screen | What to Say (Script) |
|---|---|---|---|
| **0:00 – 0:45** | **Problem Intro & Hook** | Slide 1 & 2 of `http://127.0.0.1:8001/presentation` | *"Hello judges! Every year, millions of citizens in India struggle with complex government portals like Parivahan and NSP, forcing them to share private Aadhaar and documents with cyber cafés. Today, we present JanSeva AI — an autonomous, Zero-PII web co-pilot that executes public service forms directly on your screen."* |
| **0:45 – 1:30** | **App & Zero-PII Vault** | Open `http://127.0.0.1:8001/` and expand **Profile** | *"Here is the clean Claude-style interface. Notice the citizen profile vault. When a user uploads a marksheet or ID, entities like Aadhaar and Driving License are tokenized locally. Real PII is never shared with third-party LLMs."* |
| **1:30 – 3:00** | **Live Autonomous Flow (Parivahan DL Demo)** | Click **🚗 Demo: Parivahan DL Form** -> Click **▶️ Launch Browser Co-Pilot** | *"Watch this: I click DL Renewal Demo and Launch Co-Pilot. A headed Chromium browser window opens in slow-motion. The agent scans the DOM, detects the DL Number, Date of Birth, checks the Motor Vehicles Act statutory exemption, and populates the form. Notice it pauses in Silent Mode for the visual CAPTCHA. I enter the code, click Resume, and it instantly submits and generates an official acknowledgment receipt!"* |
| **3:00 – 4:00** | **Scholarship Intake (NSP Demo)** | Click **🎓 Demo: Scholarship Form** -> Click **▶️ Launch Co-Pilot** | *"Next, we test the National Scholarship Portal intake. The agent evaluates the Central Sector Scheme rules, populates 9 academic fields, attaches the marksheet PDF, and generates a verified receipt."* |
| **4:00 – 5:00** | **Architecture & Impact** | Slide 4 & 7 of Pitch Deck | *"JanSeva AI is built with Google Gemini, Playwright, and a local Zero-PII security vault, validated across 107 passing unit tests. Our roadmap includes DigiLocker integration and Bhashini multilingual voice support for 22 Indian regional languages. Thank you!"* |

---

## 📊 7-Slide Pitch Deck Overview (`/presentation`)

- **Slide 1:** Title: *JanSeva AI — Autonomous Zero-PII Public Service Execution Agent*
- **Slide 2:** Problem: *The Crushing Friction of Digital Bureaucracy in India*
- **Slide 3:** Proposed Solution: *JanSeva AI Citizen Co-Pilot*
- **Slide 4:** Technical Architecture: *Dual-Loop LLM + Playwright Desktop Actuator*
- **Slide 5:** Safety & Guardrails: *Zero-PII Redaction, Zero-Hallucination Policy, Silent Mode*
- **Slide 6:** Live Demonstration & Test Results: *107 Passing Tests, MoRTH & NSP Workflows*
- **Slide 7:** Future Roadmap: *Bhashini Voice in 22 Languages, DigiLocker, Rural CSC Kiosks*
