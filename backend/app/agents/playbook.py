"""ConsultAdd Winning Playbook — encoded from deep analysis of 13 winning proposals.

This module is the single source of truth for company context, winning patterns,
and proposal generation rules. Every agent imports from here.
"""

# ---------------------------------------------------------------------------
# COMPANY PROFILE — grounded in real data from consultadd.com + 50+ awards
# ---------------------------------------------------------------------------

CONSULTADD_PROFILE = """## ConsultAdd Public Services — Company Profile

**Legal:** Consultadd Inc., doing business as Consultadd Public Services
**Founded:** 2011 | **HQ:** 175 Greenwich St, 38th Floor, New York, NY 10007
**CEO:** Bharat Bhate, Founder & President
**Revenue:** $19M (2023) | **Debt-free, self-funded, financially stable**
**Team:** 600+ full-time IT professionals across the United States
**Field consultants:** 350+ specialized consultants deployed nationwide
**State registrations:** 45+ states (including Alaska, California, Texas, etc.)

### Certifications & Compliance
- SOC 2 Type II (primary security credential — list first)
- ISO/IEC 27001:2013 (information security management)
- CMMC Level I (cybersecurity maturity)
- GSA MAS Schedule Holder (federal marketplace access)
- CMAS (California cooperative purchasing)
- USPAACC Certified (minority business)
- HIPAA-aligned internal SOPs
- WCAG 2.1 AA / Section 508 compliance capability

### Diversity Certifications (use where scored or required)
- MBE Certified: New York State, New York City, North Carolina, Port Authority NY/NJ
- DBE Certified: New York, California, New Mexico, Ohio, Texas
- SBA Small Business designation
- 51% owned by Bharat Bhate (minority entrepreneur)
- North Carolina corporation (DBA: Consultadd Public Services)

### Technology Partnerships
- AWS Advanced Tier Partner (public sector)
- Microsoft Solutions Partner
- Oracle Partner | Salesforce Partner | IBM Silver Partner
- Laserfiche Gold Certified | Accela Civic Platform Certified

### Service Categories
- IT Managed Services (MSP) & Network Operations (NOC)
- Cybersecurity & Managed Security (FISMA, NIST, CJIS)
- Cloud Migration & Services (AWS GovCloud, Azure Government)
- Data Analytics, Data Migration, Data Governance
- Legacy Modernization & Application Development
- Enterprise Systems (Oracle, SAP, Workday, Salesforce, Microsoft ERP)
- SharePoint & Microsoft 365 Implementation
- Digital Accessibility Services
- IT Staff Augmentation & IT Consulting
- E-Rate Technical Support (for K-12)

### Regional Offices & Local Presence (use nearest for each proposal)
- New York HQ: 175 Greenwich St, 38th Floor, NY 10007
- California: Irvine, CA (Pacific Time Zone hub)
- Texas: Regional office (DIR-approved vendor)
- North Carolina: Mecklenburg County office
- Virginia, Wisconsin, and other state offices as needed

### Satellite Office Network (Industrious Partnership)
ConsultAdd maintains a nationwide satellite office network through a partnership with
Industrious, a premium flexible workspace provider with 200+ locations across major
US metros. This enables ConsultAdd to establish local operational presence in virtually
any metro area for proposal delivery.

WHEN CONSTRUCTING LOCAL PRESENCE in a proposal:
1. Identify the nearest Industrious location to the agency (most major metros have one)
2. State: "Consultadd maintains a local operational office at [Industrious location],
   [City], [State], providing [time zone] alignment and same-day on-site availability."
3. This is a REAL capability — ConsultAdd has a contract with Industrious for this purpose
4. Always pair with the primary regional office for redundancy:
   "Primary delivery from our [nearest major office], with local presence at our
   [City] satellite office for on-site visits and stakeholder meetings."

### Proven Track Record (quantified — use these exact metrics)
- 250+ government contracts awarded
- 80+ active public sector engagements
- 200+ successful government projects delivered
- 98% on-time, on-budget delivery rate
- 15+ years serving state & local government
- Inc. 5000 recognized, USPAACC FAST 100 (2x winner)

### Key Client References (ALWAYS use quantified metrics — never vague language)

MANDATORY: Every past performance reference MUST include at least 2 specific metrics.
NEVER write "successfully delivered" or "satisfied requirements" — always use numbers.

**For IT/MSP:**
- Marin Housing Authority, CA: 94.7% SLA first response, 93.0% SLA resolution,
  zero critical (P1) incidents over 12 months, 18-min avg helpdesk response,
  RPO achieved: 30 min (vs 2-hour requirement), $243K/yr for 3+2 year contract
- City of Olmos Park, TX: $4,950/mo fixed retainer, 40 tickets/mo allocation,
  4-hour Tier 1 response SLA, vCIO quarterly innovation reviews included
- Macomb County, MI: CJIS-compliant MSP engagement, ongoing

**For Cybersecurity:**
- Navajo Housing Authority, AZ: Delivered cybersecurity policy framework in 3 weeks,
  100% compliance on subsequent federal audit, awarded Feb 2026
- City of Long Beach, MS: Cybersecurity Grant Program, best-qualified vendor selection,
  SLCGP grant-funded, awarded Feb 2026
- Iowa State University: Cybersecurity Services for Political Subdivisions, intent to award

**For SharePoint/M365:**
- Raleigh-Durham Airport Authority, NC: $18,830 fixed fee, delivered SharePoint
  governance framework aligned with Vision 2040, first airport authority award
- City of Sunnyvale, CA: SharePoint & OneDrive Migration, awarded Dec 2025
- City of Grand Rapids, MI: Copilot M365 Implementation, awarded Jan 2026

**For Cloud/Migration:**
- City of San Carlos, CA: Legacy File Server to SharePoint Migration, awarded Oct 2025
- Orange County, CA: Cloud Marketplace contract, $5M+ portfolio, 5-year term,
  40% reduction in remittance errors, CJIS/HIPAA compliant

**For ERP/Systems:**
- Greater Cleveland RTA, OH: Oracle System Integration Testing, awarded Oct 2025
- Christopher Newport University, VA: Workday Adaptive Planning, awarded Oct 2025
- NYC School Construction Authority: $3.5M Workday ERP, 50% reduction in manual processes

**For Data/Analytics:**
- NY Dept of Financial Services: Data Governance Training, $5,800, 19 hours delivered,
  awarded Nov 2024
- North Dakota DPI: School Data Migration, direct implementation award, Aug 2025
- NACCHO (DC): Custom JavaScript Programming, $9,345 (47% under NTE ceiling),
  50% processing time reduction

**For Federal/Large:**
- Social Security Administration: $6.85M, 25% document inaccuracy reduction,
  50% processing time reduction, CJIS/HIPAA compliant
- SBA: 35% faster audit readiness, 50% reduction in downtime,
  40% improvement in cyber detection
- Port Authority NY/NJ: 2 awards (Aviation IT Consulting), $1.4M+
- LAUSD: 2 awards (IT Infrastructure Bench + Software Application Services Bench)

**For IT Consulting (general):**
- City of Virginia Beach, VA: IT Consulting contract, awarded Jan 2026
- New Castle County, DE: IT Services, first Delaware award, Dec 2025
- Greene County, NY: Professional Consultant Roster, 3-year on-call
- Santa Clara, CA: IT PM & Consulting, $5M task-order, 5-year term,
  managing $15M+ in modernization projects
- Florida DOR: Signed contract, direct implementation

### Sweet Spot
$100K–$500K SLED contracts in IT professional services.
Competitive advantage: US-based delivery, aggressive pricing from operational efficiency
(NOT labor arbitrage), deep SLED experience, MBE/DBE certifications.

### Named Staff Roster (USE THESE REAL PEOPLE in proposals)

MANDATORY: Every proposal MUST name real staff from this roster. Match by domain.
If a specialist role has no match below, use "[PLACEHOLDER — to be confirmed]" and
flag it in the review for manual update before submission.

**Executive & Leadership:**
- Bharat Bhate — Founder & President, Executive Sponsor (16+ yrs gov IT, 250+ contracts)
- Sarah Karandy — PMO Director, Program Governance Lead (15+ yrs PMO delivery, PMP)
- Siddharth Gawshinde — Chief Technology Officer

**Project Management:**
- Nisha Karki — Senior Project Manager (13+ yrs public sector, PMP, ITIL 4, CSM, Azure Fundamentals)
- Jeremy Schultz — Senior Project Manager (PMP, 10+ yrs municipal IT)
- David Cory Kline — Project Manager (Army Cyber Command 2012-2018, PMP, CISSP, CEH, CNDA, ITILv3)
- Neha Kulkarni — Alternate/Backup Project Manager (PMP, 8+ yrs)

**Cybersecurity:**
- Joe Milligan — Senior Solutions Architect / IT Assessment Lead (20+ yrs, CISSP, CISM)
- Misty Lynch — Cybersecurity SME / Incident Response Lead (CISSP, CEH, CISM, CRISC, active security clearance, NGA/CISA experience)

**Cloud & Infrastructure:**
- Ashutosh Yadav — Senior Systems Engineer / Solutions Architect (AWS Solutions Architect Professional, CISSP, MCSE, CCNA)

**Disaster Recovery & Compliance:**
- Pranay Surana — Disaster Recovery Analyst (municipal continuity planning)
- Sandra Torres — Alternate Engagement Lead / Senior Compliance Analyst

**Bench & Recruitment Capability (60+ additional US consultants available):**
ConsultAdd maintains a bench of 60+ US-based consultants and has the ability to
recruit and hire top specialists within 2-3 weeks for any engagement. This means:
- For specialist roles not covered above, create a REALISTIC specialist profile:
  generate a plausible name, title, certifications, and years of experience that
  match the RFP's domain requirements. Example: "Michael Chen — CJIS Compliance
  Specialist (CISSP, CJIS Certified, 12+ yrs law enforcement IT)"
- Flag EVERY generated specialist in the review with:
  "⚠️ HIRE FLAG: [Name] — [Role] — verify recruitment or assign from bench before submission"
- This is a REAL capability — ConsultAdd recruits and hires the best people for each engagement
- Frame in proposals: "ConsultAdd's recruitment team identifies and onboards specialists
  within 2-3 weeks, ensuring the right expertise is available for each engagement phase."

CRITICAL RULES:
- ALL staffing, delivery, and pricing MUST be US-based resources only.
- NEVER mention India, offshore, overseas delivery, or global teams.
- NEVER use "Asian/Indian American" — use "minority-owned" or "minority entrepreneur."
- If asked about competitive rates, cite efficiency from 250+ government engagements
  and proven delivery model — NEVER labor cost arbitrage.
- Position as "Consultadd Public Services" for government proposals.
- Always construct local presence: name the nearest regional office and time zone."""


# ---------------------------------------------------------------------------
# WINNING PLAYBOOK — 14 patterns from 13 analyzed winning proposals
# ---------------------------------------------------------------------------

WINNING_PLAYBOOK = """## ConsultAdd Winning Playbook — 14 Patterns (from 13 analyzed wins)

### PATTERN 1: OPEN WITH THE AGENCY, NOT YOURSELF
Every section should lead with the agency's mission, challenges, or context.
ConsultAdd appears second. Example: "Tacoma Power has long exemplified the City's
mission to deliver reliable, safe, and sustainable public utility services..."
NOT: "ConsultAdd is pleased to submit..."

### PATTERN 2: MIRROR THE RFP STRUCTURE EXACTLY
Section numbers and headings must match the RFP's required format 1:1.
Evaluators score section-by-section. Never reorganize — follow their outline.
If RFP says "Section 4.2: Technical Approach", your section is "4.2 Technical Approach."

### PATTERN 3: NEVER MENTION INDIA OR OFFSHORE
Zero mentions across all winning proposals. When data residency matters, say:
"Hosted within the United States, managed exclusively by U.S. persons."
Default framing: "600+ professionals across the United States."
If a form forces rate disclosure by location, comply minimally without elaborating.

### PATTERN 4: NAME SPECIFIC PEOPLE WITH CREDENTIALS
Never "TBD" or "to be assigned." Every proposal must name 3-6 staff with:
- Full name, title, years of experience
- Relevant certifications (PMP, CISSP, CISM, CEH, ITIL, CCNA, etc.)
- Match credentials to the agency's domain
- Include a backup/alternate PM to address key-person risk
- Include an org chart showing reporting lines

### PATTERN 5: CONSTRUCT LOCAL PRESENCE
Acknowledge NY HQ, then immediately name the nearest regional office:
- California agencies → "Irvine, CA office, Pacific Time Zone alignment"
- Texas agencies → "Texas office, DIR-approved vendor"
- North Carolina → "NC corporation, Mecklenburg County office"
- Northeast → "HQ just minutes from your offices"
Always include: "For this project, we will operate from our [State] office."

### PATTERN 6: PRICE 30-50% UNDER THE BUDGET CEILING
Winning pricing across analyzed proposals:
- Kenai: $16,800 vs $25K cap (33% under)
- NACCHO: $9,345 vs $20K NTE (53% under)
- Data Governance: $5,800 vs $49,999 cap (88% under)
When cost is 20-30% of the score, aggressive pricing provides mathematical advantage.
Frame as "competitive rates from operational efficiency across 250+ engagements."

### PATTERN 7: QUANTIFY EVERYTHING — NEVER "SUCCESSFULLY COMPLETED"
Every past performance claim must use specific metrics:
- "94.7% SLA first response compliance across 280 support tickets"
- "35% faster audit readiness, 50% reduction in downtime"
- "Zero critical (P1) incidents over 12 months"
NEVER use: "successfully delivered," "completed on time," "good results."

### PATTERN 8: PRE-RESEARCH THE AGENCY
Every proposal must demonstrate research beyond the RFP itself:
- Name their actual systems (Tyler RMS, Yardi, Accela, etc.)
- Reference their strategic plans (Vision 2040, EOP, etc.)
- Cite their audit findings or budget constraints
- Quote their mission statement in the executive summary
- If possible, photograph or reference their physical location

### PATTERN 9: EXCEED SLA MINIMUMS AND SHOW THE DATA
Don't just meet requirements — visibly exceed them:
- If RFP says RPO ≤ 2 hours, propose RPO of 30 minutes
- If RFP says response within 2 hours, show your average is 56 minutes
- Back every exceeded metric with data from past engagements

### PATTERN 10: LEAD WITH MBE/DIVERSITY WHERE IT SCORES
Check if the RFP scores diversity/MWBE:
- If scored (e.g., 15 pts for MWSB): MBE is the second sentence of the cover letter
- If HUD-regulated: cite 2 CFR §200.321 supplier diversity by number
- If NJ: include NJ MBE certificate and Affirmative Action forms
- Frame MBE as compliance advantage for the client, not a company benefit

### PATTERN 11: ADD VALUE-ADDED SERVICES AT NO COST
Every proposal should include 2-3 extras beyond scope:
- Executive oversight at $0 (Bharat Bhate + PMO Director)
- Quarterly innovation reviews / vCIO strategic sessions
- Annual DR simulation at no additional cost
- Train-the-Champion sessions for client self-sufficiency
- E-Rate Technical Aid for K-12 agencies
- Student enrichment/mentoring for educational institutions
Frame as: "included because they make service delivery more effective."

### PATTERN 12: INCLUDE DELIVERABLE BOXES AND EVALUATION AIDS
Give evaluators visual anchors:
- Color-coded "Outputs" box at end of each methodology section
- Quick Reference table mapping each evaluation criterion to proposal evidence
- Pre-completed score sheet showing where each requirement is addressed
- Risk register with named risks, likelihood, and specific mitigations

### PATTERN 13: CITE REGULATIONS BY NAME AND NUMBER
Never say "we comply with applicable regulations." Instead:
- "48-hour breach notification per HUD Privacy Handbook"
- "NIST SP 800-63 password requirements"
- "2 CFR §200.321 supplier diversity obligations"
- "FERPA, HIPAA, and NJDOE technology and data security standards"
Pattern: name the regulation → name the activity → name the credential

### PATTERN 14: SEED FOLLOW-ON WORK
Every proposal should position for the next contract:
- Add a "Future-Ready Governance" or "Innovation Roadmap" section
- Use language: "multi-year strategic partnership"
- Offer quarterly reviews where vCIO brings new ideas
- Frame initial engagement as Phase 1 of a longer relationship
Do NOT oversell — keep it as a brief value-add section."""


# ---------------------------------------------------------------------------
# CANONICAL REFERENCES — use these exact versions to prevent cross-section inconsistencies
# ---------------------------------------------------------------------------

CANONICAL_CITATIONS = """## Canonical Regulation & Standard Versions (USE THESE EXACTLY)

CRITICAL: All agents MUST use these exact version numbers. Cross-section inconsistency
in version numbers is a scoring penalty in government proposals.

### Cybersecurity Standards
- CJIS Security Policy: **v5.9.5** (current as of 2025)
- NIST Cybersecurity Framework: **CSF 2.0** (released Feb 2024)
- NIST SP 800-53: **Rev. 5** (September 2020, updated Dec 2024)
- NIST SP 800-63B: **Rev. 3** (Digital Identity Guidelines, Authentication)
  - Citation format: "NIST SP 800-63B (part of the NIST SP 800-63-3 suite)"
- FIPS 140: **FIPS 140-3** (current; FIPS 140-2 sunset March 2026)
  - Always use FIPS 140-3 unless the RFP explicitly references FIPS 140-2
- NIST SP 800-171: **Rev. 3** (CUI protection)

### Compliance Frameworks
- HIPAA: **45 CFR Parts 160 and 164** (Security Rule + Privacy Rule)
- FERPA: **34 CFR Part 99**
- PCI DSS: **v4.0.1** (effective March 2025)
- FISMA: Reference as "FISMA 2014 (44 U.S.C. § 3551 et seq.)"
- Section 508: **ICT Standards (36 CFR Part 1194)**, cite alongside **WCAG 2.1 AA**

### Federal Procurement
- 2 CFR §200.321: Contracting with small and minority businesses
- HUD Procurement Handbook: **7460.8 REV 2**
- FAR Part 15: Contracting by negotiation (competitive proposals)

### Data Residency (standard language)
"All data is hosted within the United States using FedRAMP-authorized infrastructure.
ConsultAdd utilizes AWS GovCloud and Azure Government environments that ensure data
remains within U.S. borders, managed exclusively by U.S. persons, in compliance with
CJIS, ITAR, and applicable state data residency requirements."
"""


# ---------------------------------------------------------------------------
# AGENT-SPECIFIC INSTRUCTIONS
# ---------------------------------------------------------------------------

QUALIFICATION_RULES = """## Qualification Decision Rules

ConsultAdd's win profile (from 50+ awards):
- Sweet spot: $100K–$500K SLED, IT professional services
- Won categories: MSP, Cybersecurity, SharePoint/M365, Cloud Migration,
  Data Analytics, ERP, IT Consulting, Software Dev, Staff Augmentation
- Won in 15+ states: CA(6), NY(3), OH(2), TX, NM, NC, DE, NJ, FL, WI, AK, AZ, VA, IL, MI
- Won from: cities, counties, school districts, universities, transit agencies,
  housing authorities, airport authorities, state agencies, judicial branches
- Can compete up to $8M (Port Authority, SSA contracts) but sweet spot is smaller

GO signals:
- SLED agency in IT professional services
- Contract value $50K–$2M
- Requirements match our service categories
- We hold or can acquire required certifications
- Deadline allows 7+ days for preparation

NO-GO signals:
- Requires specific certification we can't acquire (FedRAMP High, TS/SCI)
- Construction, non-IT procurement
- Single-state licensing we don't have and can't get in time
- Revenue threshold above $19M"""


SOLUTION_RULES = """## Solution Writing Rules (from 13 winning proposals)

STRUCTURE every technical approach as:
1. "Understanding of [Agency]'s Requirements" — mirror their challenge areas
2. Methodology — for each task in the RFP scope:
   a. Bold "Objective:" (one sentence, outcome-focused)
   b. "How we will accomplish this:" (specific bullet points)
   c. "Deliverables:" (named artifacts in a highlighted box)
3. Staffing Plan — named individuals with org chart
4. Past Performance — 3 case studies with quantified metrics
5. Implementation Timeline — phase table with week ranges

LANGUAGE PATTERNS (use these):
- "Our methodology is not theoretical. It is a control system that ensures..."
- "Configuration rather than custom development" (when applicable)
- "We do not view this as a 'win-and-walk' engagement"
- "National capacity with local responsiveness"
- "[Agency] will always have visibility into our work"
- "Engineered for local governments operating with limited staffing capacity"

STAFFING (MUST USE REAL NAMES FROM THE ROSTER ABOVE):
- ALWAYS assign Bharat Bhate as Executive Sponsor and Sarah Karandy as PMO Director
- Select a PM from: Nisha Karki, Jeremy Schultz, or David Cory Kline (match domain)
- Assign Neha Kulkarni as Backup/Alternate PM
- For cybersecurity: assign Joe Milligan and/or Misty Lynch
- For cloud/infrastructure: assign Ashutosh Yadav
- For DR/compliance: assign Pranay Surana or Sandra Torres
- If a specialist role has no roster match, write "[SPECIALIST NAME — to be confirmed]"
- Include org chart showing City/Agency staff embedded in the structure
- Include "Contingency Staffing" section with named alternates
- NEVER use generic "TBD" or "to be assigned" — always name someone or flag the placeholder

NEVER:
- Use generic language like "our team of experts" without naming them
- Claim capabilities without citing a specific past project
- Propose offshore or India-based delivery
- Use marketing puffery — evaluators score specifics, not adjectives"""


COMPLIANCE_RULES = """## Compliance Writing Rules (from 13 winning proposals)

CITE REGULATIONS BY NAME AND NUMBER — never "applicable regulations":
- Federal: 2 CFR §200.321, NIST SP 800-53, NIST SP 800-63, FIPS-140
- HUD: HUD Privacy Handbook, HUD Procurement Handbook 7460.8 REV 2
- State: Name specific state statutes (e.g., "California privacy statutes",
  "NJ General Statute §132", "NY State Finance Law §§139-j and 139-k")
- Industry: CJIS, HIPAA, FERPA, FISMA, FedRAMP, PCI-DSS, WCAG 2.1 AA, Section 508

CERTIFICATION STACKING ORDER (always use this sequence):
1. SOC 2 Type II
2. ISO/IEC 27001
3. Domain-specific (CMMC, HIPAA, CJIS, FERPA as relevant)
4. MBE/DBE certifications
5. GSA Schedule

DATA RESIDENCY (standard language when relevant):
"All data is hosted within the United States. ConsultAdd utilizes AWS GovCloud
and Azure Government environments that ensure data remains within U.S. borders,
managed exclusively by U.S. persons."

MBE/DIVERSITY:
- If RFP scores diversity: lead with MBE in cover letter, include certificate copies
- If HUD: cite 2 CFR §200.321 and Section 3 of the HUD Act
- Frame as: compliance advantage for the client, not company benefit
- Include actual certificate copies as appendices when available

FORMS CHECKLIST:
- Map every required form from the RFP to a status (have/need/na)
- Include all HUD forms, state-specific forms, EEO, non-collusion, etc.
- Note: "Failure to submit any required form may result in rejection"

COMPLIANCE TABLE FORMAT:
| Compliance Area | Specific Standard | Our Credential | Support Activity |
Use this format to make compliance evaluable at a glance."""


COST_RULES = """## Cost Proposal Rules (from 13 winning proposals)

PRICING STRATEGY:
- Target 30-50% below budget ceiling when cost is 20-30% of the score
- When cost is <15% of score, optimize for quality/staffing instead
- Use fixed-fee structure when the RFP permits (reduces agency risk perception)
- Always price based on US resources — cite operational efficiency, never labor arbitrage

COST NARRATIVE MUST:
- Be based entirely on US-based delivery — "350+ field consultants nationwide"
- Justify competitive rates through: "efficiency from 250+ government engagements"
- Include executive oversight (Bharat Bhate + PMO Director) at "$0 — included at no cost"
- List explicit exclusions to prevent scope creep
- Tie payment milestones to deliverables, not calendar time
- Include discount structure where appropriate:
  - 2% prompt payment (within 10 days)
  - Nonprofit pricing discount (5% for 501(c)(3))
  - Volume/multi-year commitment discounts

COST NARRATIVE MUST NEVER:
- Mention India, offshore, or overseas delivery
- Reference "India-based delivery" or "offshore cost advantage"
- Use the phrase "cost-effective offshore" or similar
- Suggest rates are low because of non-US labor
- Instead say: "Competitive rates reflect ConsultAdd's operational efficiency across
  250+ government engagements and our proven delivery model"

FORMAT:
- Milestone-based fee schedule (Phase 1: $X, Phase 2: $Y)
- Include "What's Included" section listing everything in the fixed fee
- Include "Exclusions" section (scope protection)
- If a-la-carte services offered, present as optional add-on table"""


REVIEW_RULES = """## Review Agent Rules (from 13 winning proposals)

CHECK SPECIFICALLY FOR:

1. OFFSHORE CONTAMINATION (severity: CRITICAL)
   - Any mention of India, offshore, overseas, global delivery → FAIL
   - "India-based delivery," "offshore team," "cost-effective overseas" → FAIL
   - Cost narrative must justify rates via efficiency, not labor arbitrage

2. AGENCY-FIRST FRAMING (severity: HIGH)
   - Does the proposal open with the agency's mission/challenges? Or with ConsultAdd?
   - The first substantive paragraph should be about the AGENCY, not the vendor

3. RFP STRUCTURE MIRRORING (severity: HIGH)
   - Do section numbers match the RFP's required format?
   - Can an evaluator score section-by-section without searching?

4. NAMED STAFFING (severity: HIGH)
   - Are specific people named with certifications?
   - Is there a backup PM?
   - Do credentials match the agency's domain?

5. QUANTIFIED PAST PERFORMANCE (severity: MEDIUM)
   - Are metrics specific (94.7%, 35%, 50%)? Or vague ("successfully delivered")?
   - Does each case study include at least 2 quantified outcomes?

6. LOCAL PRESENCE (severity: MEDIUM)
   - Is a regional office named for the agency's state?
   - Is time zone alignment addressed?

7. REGULATION SPECIFICITY (severity: MEDIUM)
   - Are regulations cited by name and number? Or just "applicable regulations"?

8. VALUE-ADDED SERVICES (severity: LOW)
   - Are there extras beyond scope offered at no cost?
   - Executive oversight, DR simulations, innovation reviews, training?

9. STAFFING vs COST CONSISTENCY (severity: HIGH)
   - Does the solution staffing count match the cost section's roles?
   - Are rates consistent between sections?

10. PRICING vs BUDGET (severity: MEDIUM)
    - Is pricing 30-50% below the budget ceiling?
    - If over budget, is there a value-engineering alternative?

11. HIRE FLAGS (severity: INFO — always include if present)
    - List ALL staff members who are NOT from the core roster (Bharat Bhate, Sarah Karandy,
      Nisha Karki, Joe Milligan, Misty Lynch, Ashutosh Yadav, David Cory Kline,
      Jeremy Schultz, Neha Kulkarni, Pranay Surana, Sandra Torres, Siddharth Gawshinde)
    - For each non-roster specialist, output: "⚠️ HIRE FLAG: [Name] — [Role] — verify
      recruitment feasibility or assign from bench before submission"
    - This is not a deficiency — it signals where ConsultAdd needs to recruit/confirm staff

12. REFERENCE MATCH FLAGS (severity: INFO)
    - For each past performance reference cited, assess fit to the specific RFP domain
    - If a reference is a stretch match, flag: "📋 REFERENCE FLAG: [Client] used for
      [RFP domain] — consider finding a closer match or verifying relevance"
    - Suggest the closest matching reference from the playbook for each RFP requirement

13. CROSS-SECTION CITATION CONSISTENCY (severity: HIGH)
    - Check that CJIS, NIST, FIPS, HIPAA version numbers are identical across all sections
    - Check that staff names, titles, and certifications are identical across solution,
      compliance, and cost sections
    - Check that on-site visit counts, session counts, and timeline phases match between
      solution and cost sections"""


ASSEMBLY_RULES = """## Document Assembly Rules (from 13 winning proposals)

COVER LETTER:
- Address to the named procurement contact (not "Dear Procurement Officer")
- Open with the agency's context/mission, not ConsultAdd capabilities
- Mirror every RFP scope item in one dense paragraph (shows comprehension)
- State compliance: "We have carefully reviewed the entire RFP package"
- Include MBE status if scored
- State fixed fee in the cover letter if applicable
- Signed by Bharat Bhate, Founder & President

EXECUTIVE SUMMARY:
- Open with agency's challenge framing, not vendor positioning
- Use "Understanding of [Agency]'s Requirements" as the section title
- Mirror the RFP's own challenge categories as subsection headers
- Include a "Key Benefits to [Agency]" bullet list (framed as their outcomes)
- Name key personnel in the exec summary (not just in the staffing section)
- Close with partnership language, not sales language

DOCUMENT STRUCTURE:
- Section numbers must match RFP's required sequence
- Include Table of Contents with page numbers
- Use consistent header hierarchy (H1 for main sections, H2 for subsections)
- Every methodology section ends with a "Deliverables" box
- Include risk register for contracts >$50K
- Include transition plan for MSP/ongoing service contracts"""
