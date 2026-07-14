# Research sources and prior art

Status: initial source register  
Retrieved/rechecked: 2026-07-13  
Owner: clinical evidence lead  
Rule: recheck primary sources before encoding an assertion or making an external claim

This register supports product scope and hazards. It does not by itself approve a clinical oracle. Approval and validity rules are in [Governance](07-GOVERNANCE-LEGAL-SAFETY.md).

## Standards and official guidance

### HL7 Gender Harmony

- [HL7 Cross Paradigm Gender Harmony implementation guide](https://build.fhir.org/ig/HL7/fhir-gender-harmony/): defines the model and guidance for Gender Identity, Sex Parameter for Clinical Use, Recorded Sex or Gender, Name to Use, and Pronouns across HL7 paradigms. The build site warns that it changes continuously; pin a published package or commit for test evidence.
- [FHIR guidance and artifact summary](https://build.fhir.org/ig/HL7/fhir-gender-harmony/fhirgenderharmony.html): describes FHIR extensions and use of HumanName.use equal to usual for Name to Use.
- [Gender Harmony logical model](https://build.fhir.org/ig/HL7/fhir-gender-harmony/model.html): definitions, context, cardinality, and limitations for the five concepts.
- [HL7 v2 Gender Harmony guidance](https://build.fhir.org/ig/HL7/fhir-gender-harmony/hl7v2genderharmony.html): covers v2 representations and the need for bilateral agreement when pre-adopting newer profile components in earlier versions.

Use: semantic separation and interoperability fixtures.  
Limit: the guide does not prove an installed workflow is correct and does not prescribe a universal patient-specific range.

### DICOM

- [DICOM Supplement 233: Patient Model Gender Enhancements](https://www.dicomstandard.org/news-dir/current/docs/sups/sup233.pdf): harmonizes imaging patient-model concepts with Gender Harmony and updates Patient Sex semantics.

Use: P2 RIS/DICOM research only.  
Limit: v1 does not execute DICOM assertions.

### ASTP/ONC test guidance

- [Patient demographics and observations test method](https://healthit.gov/test-method/patient-demographics-and-observations): describes certification-test outcomes for demographics/observations, including SPCU, Name to Use, and Pronouns, with current clarifications.

Use: regulatory/certification landscape and technical prior art.  
Limit: requirements and enforcement may change; ContextSafe is not an ASTP/ONC certification.

### FDA

- [Clinical Decision Support Software, January 2026 final guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software): FDA's current guidance page for device and non-device CDS scope; content current as of January 29, 2026.

Use: intended-use legal analysis; the RG-19 counsel memo must analyze the January 2026 guidance against shipped functions and claims.  
Limit: guidance is not a product-specific determination; counsel must assess actual functionality and claims.

## Safety and clinical evidence

- [Reference Ranges for All: Implementing Reference Ranges for Transgender and Nonbinary Patients](https://pmc.ncbi.nlm.nih.gov/articles/PMC11655151/): case report of an X value reaching an LIS with no configured range, leading to absent reference ranges and abnormal flags; discusses a local mitigation.

Use: motivates CTP-012 and the blank-range/flag hazard.  
Limit: one institution and local configuration; its mitigation is not encoded as universal clinical advice.

- [Approach to Interpreting Common Laboratory Pathology Tests in Transgender Individuals](https://pmc.ncbi.nlm.nih.gov/articles/PMC7947878/): reviews context-specific interpretation questions and uncertainty for common laboratory tests.

Use: shows why clinical context and organ/hormone-relevant evidence cannot be inferred from GI alone.  
Limit: recommendations and evidence vary by analyte and patient; independent current review is required.

- [Preferred Names, Preferred Pronouns, and Gender Identity in the Electronic Medical Record and Laboratory Information System: Is Pathology Ready?](https://pmc.ncbi.nlm.nih.gov/articles/PMC5653959/): describes pathology/EHR/LIS identity and reference-interval concerns.

Use: hazard inventory and service research.  
Limit: older publication; recheck current systems and guidance.

- [Analysis of laboratory data transmission between two healthcare institutions](https://pmc.ncbi.nlm.nih.gov/articles/PMC11042873/): documents information loss including units, reference ranges, and coding across laboratory data exchange.

Use: supports checkpoint-level provenance and non-gender-specific interoperability risk.  
Limit: not specifically a trans/nonbinary test pack.

## Adjacent tools and substitutes

- [Inferno on HealthIT.gov](https://fhir.healthit.gov/): open-source FHIR conformance test framework and hosted test kits; its public instance excludes sensitive data/PHI.

Use: prior art and potential complementary conformance evidence. ContextSafe should not recreate a general FHIR conformance framework.

- [Synthea](https://github.com/synthetichealth/synthea): open-source synthetic patient population generator producing formats including FHIR.

Use: establishes synthetic patient generation as prior art and potential fixture input. ContextSafe's fixed pack is an oracle-controlled test set, not a population simulator.

- [Synset](https://www.synset.ai/): commercial synthetic clinical worlds and QA/audit packaging.

Use: establishes commercial synthetic clinical QA prior art and must be monitored as an adjacent competitor or partner.

- [The Leapfrog Group diagnostic excellence initiative](https://www.leapfroggroup.org/influencing/recognizing-excellence-diagnosis): patient-safety and diagnostic-excellence practices, surveys, and transparency.

Use: buyer/channel and broader patient-safety context. ContextSafe does not reproduce a facility survey or grade.

## Novelty and claims conclusion

The public landscape demonstrates that:

- synthetic patient generation is not novel;
- FHIR and certification conformance testing are not novel;
- Gender Harmony and DICOM representations are published standards;
- hospitals and vendors already perform interface and regression testing;
- patient-safety measurement is an established field.

The hypothesis to validate is narrower: a packaged, clinically and trans-community-governed test pack that runs across an installed registration → EHR → HL7/FHIR → LIS pathway and leaves a signed release receipt. Describe this as a differentiated vertical hypothesis, not “the first,” “unique,” or “no competitor.”

## Source maintenance

For every source used by a released assertion, record:

- source ID and exact claim supported;
- stable identifier/URL;
- publisher and author;
- publication/version/effective date;
- retrieval date and content hash where licensing permits;
- normative/informative/local status;
- limitations and counterevidence;
- named verifier;
- next review date;
- superseded/withdrawn state.

Automated monitoring may identify change, but a qualified human must determine whether the assertion changes. A broken or stale source blocks the assertion if its support cannot be independently re-established.
