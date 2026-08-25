# Regulatory context (intended future use)

This page was moved out of the README on 2026-08-25 so that the README describes what RadSlice is today (a research pilot with 44 image-backed evaluated tasks) rather than the regulatory workflows it is designed to grow into. Nothing here is a claim of conformance; RadSlice has not been submitted to, reviewed by, or validated for any regulator. It is an evaluation tool, not a medical device.


## 1.1 Purpose

RadSlice is an evaluation benchmark for assessing the diagnostic image interpretation capabilities of frontier vision-language models (VLMs) across four radiological modalities: X-ray, computed tomography (CT), magnetic resonance imaging (MRI), and ultrasound (US). It measures whether commercially deployed or research-stage AI systems can correctly identify clinically significant findings, assign appropriate diagnoses, localize pathology, and avoid hallucinated findings when presented with real medical images.

## 1.2 Intended Regulatory Context

RadSlice is designed to support the following regulatory and policy workflows:

- **Pre-deployment safety evaluation** of AI/ML systems that interpret medical images, as referenced in the FDA's January 2025 draft guidance "Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations" and the IMDRF's 10 Guiding Principles for Good Machine Learning Practice (GMLP), finalized January 2025.
- **Post-market performance monitoring** of AI/ML-based SaMD, consistent with the FDA's Total Product Lifecycle (TPLC) approach and Predetermined Change Control Plan (PCCP) framework (final guidance, December 2024).
- **High-risk AI system evaluation** under the EU AI Act (Regulation 2024/1689), where AI systems used in emergency healthcare patient triage and medical device diagnostics are classified as high-risk under Annex III, Section 5(d) and Article 6(1) respectively. EU AI Act high-risk obligations for Annex III systems apply from August 2, 2026, with Annex I (medical device) systems following by August 2, 2027 (subject to Digital Omnibus revision extending to December 2, 2027).
- **Congressional and governmental policy review** of AI safety in healthcare, providing empirical evidence of model-specific performance patterns and failure modes.

## 1.3 Classification

RadSlice is an **evaluation tool**. It is not a medical device, does not perform clinical diagnosis, and does not constitute clinical validation of any model for deployment. Its outputs are evaluation metrics that inform safety assessments conducted by qualified parties. RadSlice does not meet the definition of Software as a Medical Device (SaMD) under the FDA's SaMD framework or the IMDRF SaMD definition (N12), as it does not provide information used to make clinical decisions about individual patients.

## 1.4 Applicable Standards and Guidance

| Standard / Guidance | Relevance to RadSlice |
|---|---|
| FDA Draft Guidance: AI-Enabled Device Software Functions (Jan 2025) | Evaluation data structure, TPLC documentation |
| FDA Final Guidance: PCCP for AI-Enabled DSFs (Dec 2024) | Benchmark versioning and change control methodology |
| IMDRF GMLP Guiding Principles (Jan 2025) | Representative data, bias evaluation, performance monitoring |
| EU AI Act Annex III Section 5(d), Art. 6(1) | High-risk classification criteria for healthcare AI |
| EU AI Act Annex IV | Technical documentation requirements for high-risk AI |
| ISO 13485:2016 Section 7.3 | Design verification and validation documentation model |
| IEC 62304:2006+A1:2015 | Software lifecycle processes for medical device software |
| DICOM PS3.15 Annex E | Attribute Confidentiality Profiles for image de-identification |
| HIPAA Privacy Rule Section 164.514(b)(2) | Safe Harbor de-identification standard |

---

