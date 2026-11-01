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
https://garv25667.github.io/autonomous-public-service-agent/
```
*(Alternative Live Tunnel to Local Machine: `https://witty-rocks-peel.loca.lt` — Tunnel password if prompted: `45.124.188.210`)*

---

### 5. Demo video link *
*(Paste your YouTube or Google Drive video link after recording following the 5-minute script below)*

---

### 6. Public GitHub *
```text
https://github.com/Garv25667/autonomous-public-service-agent
```

---

### 7. Presentation / pitch deck link *
```text
https://garv25667.github.io/autonomous-public-service-agent/presentation.html
```
*(Alternative Live Tunnel: `https://witty-rocks-peel.loca.lt/presentation` — You can also export this 7-slide deck to PDF directly via the 🖨️ Export PDF button on the page)*

---

## 🎬 5-Minute Video Recording Walkthrough Script

Use this exact structure to record a smooth, high-scoring demo video:

| Timestamp | Section | What to Show on Screen | What to Say (Script) |
|---|---|---|---|
| **0:00 – 0:45** | **Problem Intro & Hook** | Slide 1 & 2 of Pitch Deck (`/presentation.html`) | *"Hello judges! Every year, millions of citizens in India struggle with complex government portals like Parivahan and NSP, forcing them to share private Aadhaar and documents with cyber cafés. Today, we present JanSeva AI — an autonomous, Zero-PII web co-pilot that executes public service forms directly on your screen."* |
| **0:45 – 1:30** | **App & Zero-PII Vault** | Open the Live Prototype and expand **Profile** | *"Here is the split-screen interface. On the left is the AI Co-Pilot; on the right is the actual government portal viewport. Notice the citizen profile vault: sensitive numbers like Aadhaar and Driving License are kept confidential and tokenized locally. Real PII is never shared with third-party LLMs."* |
| **1:30 – 3:00** | **Live Autonomous Flow (Parivahan DL Renewal)** | Click **⚡ Autofill Form in Real Time (Watch Live)** | *"Watch this: I click 'Autofill Form in Real Time'. The autonomous agent immediately reads the citizen vault, verifies the Motor Vehicles Act statutory Form 1A age exemption, selects Rajasthan RTO RJ01, and types the citizen's license credentials directly into the form fields with live glowing indicators. It enters the verification code, submits the form, and instantly displays the official government acknowledgment receipt with reference ID DL-RJ01-2026-904821!"* |
| **3:00 – 4:00** | **Scholarship Intake (NSP Demo)** | Switch service to **🎓 Scholarship** -> Click **⚡ Autofill Now** | *"Next, we switch to the National Merit Scholarship Portal. The agent evaluates the Central Sector Scheme merit criteria (above 80th percentile), verifies academic credentials (82.5% B.Tech record), populates the multi-section applicant intake form, and submits the application, generating a verified receipt."* |
| **4:00 – 5:00** | **Architecture & Impact** | Slide 4 & 7 of Pitch Deck | *"JanSeva AI is built with Google Gemini, Playwright, and a local Zero-PII security vault, validated across 107 passing unit tests. Our roadmap includes DigiLocker integration and Bhashini multilingual voice support for 22 Indian regional languages. Thank you!"* |

---

## ⚙️ How to Activate GitHub Pages (1-Click Setup)
If GitHub Pages is not yet enabled on your repo:
1. Go to your repository settings: **https://github.com/Garv25667/autonomous-public-service-agent/settings/pages**
2. Under **Build and deployment**:
   - **Source**: `Deploy from a branch`
   - **Branch**: `main`
   - **Folder**: `/docs`
3. Click **Save**.
Within ~30 seconds, GitHub automatically hosts the live prototype at `https://garv25667.github.io/autonomous-public-service-agent/`!
