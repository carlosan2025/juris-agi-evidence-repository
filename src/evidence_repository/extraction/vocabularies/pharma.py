"""Pharmaceutical/Life Sciences vocabulary for due diligence extraction."""

from evidence_repository.extraction.vocabularies.base import (
    BaseVocabulary,
    ClaimPredicate,
    MetricDefinition,
    RiskCategory,
)


class PharmaVocabulary(BaseVocabulary):
    """Pharmaceutical/Life Sciences due diligence vocabulary.

    Focused on metrics, claims, and risks relevant to pharma/biotech
    investments, clinical trials, and regulatory compliance.
    """

    @property
    def profile_code(self) -> str:
        return "pharma"

    @property
    def profile_name(self) -> str:
        return "Pharmaceutical/Life Sciences"

    def get_metrics(self, level: int = 1) -> list[MetricDefinition]:
        """Get pharma-specific metrics by extraction level."""
        all_metrics = [
            # L1: Basic financial and pipeline metrics
            MetricDefinition(
                name="revenue",
                display_name="Revenue",
                description="Total revenue",
                unit_type="currency",
                aliases=["sales", "net_revenue"],
                required_level=1,
            ),
            MetricDefinition(
                name="rd_spend",
                display_name="R&D Spend",
                description="Research and development expenditure",
                unit_type="currency",
                aliases=["research_development", "r_and_d", "rd_expense"],
                required_level=1,
            ),
            MetricDefinition(
                name="pipeline_count",
                display_name="Pipeline Count",
                description="Number of drugs in development pipeline",
                unit_type="count",
                aliases=["pipeline_size", "drug_candidates"],
                required_level=1,
            ),
            MetricDefinition(
                name="cash",
                display_name="Cash Position",
                description="Cash and cash equivalents",
                unit_type="currency",
                aliases=["cash_on_hand", "cash_balance"],
                required_level=1,
            ),
            MetricDefinition(
                name="burn",
                display_name="Cash Burn",
                description="Monthly/quarterly cash burn rate",
                unit_type="currency",
                aliases=["burn_rate", "cash_burn"],
                required_level=1,
            ),
            # L2: Clinical and market metrics
            MetricDefinition(
                name="clinical_trial_count",
                display_name="Clinical Trials",
                description="Number of active clinical trials",
                unit_type="count",
                aliases=["active_trials", "ongoing_trials"],
                required_level=2,
            ),
            MetricDefinition(
                name="phase1_count",
                display_name="Phase 1 Candidates",
                description="Drugs in Phase 1 trials",
                unit_type="count",
                aliases=["phase_1", "p1_candidates"],
                required_level=2,
            ),
            MetricDefinition(
                name="phase2_count",
                display_name="Phase 2 Candidates",
                description="Drugs in Phase 2 trials",
                unit_type="count",
                aliases=["phase_2", "p2_candidates"],
                required_level=2,
            ),
            MetricDefinition(
                name="phase3_count",
                display_name="Phase 3 Candidates",
                description="Drugs in Phase 3 trials",
                unit_type="count",
                aliases=["phase_3", "p3_candidates"],
                required_level=2,
            ),
            MetricDefinition(
                name="approved_drugs",
                display_name="Approved Drugs",
                description="Number of FDA/EMA approved drugs",
                unit_type="count",
                aliases=["marketed_drugs", "commercialized_products"],
                required_level=2,
            ),
            MetricDefinition(
                name="patent_count",
                display_name="Patent Count",
                description="Number of active patents",
                unit_type="count",
                aliases=["patents", "ip_portfolio"],
                required_level=2,
            ),
            # L3: Detailed clinical metrics
            MetricDefinition(
                name="patient_enrollment",
                display_name="Patient Enrollment",
                description="Total patients enrolled in trials",
                unit_type="count",
                aliases=["enrolled_patients", "trial_enrollment"],
                required_level=3,
            ),
            MetricDefinition(
                name="efficacy_rate",
                display_name="Efficacy Rate",
                description="Primary endpoint success rate",
                unit_type="percentage",
                aliases=["response_rate", "success_rate"],
                required_level=3,
            ),
            MetricDefinition(
                name="safety_events",
                display_name="Safety Events",
                description="Serious adverse events count",
                unit_type="count",
                aliases=["sae_count", "adverse_events"],
                required_level=3,
            ),
            MetricDefinition(
                name="manufacturing_capacity",
                display_name="Manufacturing Capacity",
                description="Production capacity",
                unit_type="count",
                aliases=["production_capacity", "cmo_capacity"],
                required_level=3,
            ),
            MetricDefinition(
                name="tam",
                display_name="Total Addressable Market",
                description="Market size for target indications",
                unit_type="currency",
                aliases=["market_size", "addressable_market"],
                required_level=3,
            ),
            # L4: Advanced metrics
            MetricDefinition(
                name="cost_per_patient",
                display_name="Cost Per Patient",
                description="Trial cost per enrolled patient",
                unit_type="currency",
                aliases=["patient_cost", "enrollment_cost"],
                required_level=4,
            ),
            MetricDefinition(
                name="time_to_market",
                display_name="Time to Market",
                description="Estimated months to FDA approval",
                unit_type="duration",
                aliases=["approval_timeline"],
                required_level=4,
            ),
            MetricDefinition(
                name="peak_sales",
                display_name="Peak Sales Estimate",
                description="Projected peak annual sales",
                unit_type="currency",
                aliases=["peak_revenue", "peak_sales_estimate"],
                required_level=4,
            ),
        ]
        return [m for m in all_metrics if m.required_level <= level]

    def get_claim_predicates(self, level: int = 1) -> list[ClaimPredicate]:
        """Get pharma-specific claim predicates by extraction level."""
        all_predicates = [
            # L1: Basic regulatory claims
            ClaimPredicate(
                name="has_fda_approval",
                display_name="FDA Approved",
                description="Drug has FDA approval",
                subject_types=["drug", "product"],
                object_types=["approval"],
                required_level=1,
            ),
            ClaimPredicate(
                name="has_ema_approval",
                display_name="EMA Approved",
                description="Drug has EMA approval",
                subject_types=["drug", "product"],
                object_types=["approval"],
                required_level=1,
            ),
            ClaimPredicate(
                name="gmp_compliant",
                display_name="GMP Compliant",
                description="Manufacturing is GMP compliant",
                subject_types=["company", "facility"],
                object_types=["certification"],
                required_level=1,
            ),
            ClaimPredicate(
                name="has_ind",
                display_name="Has IND",
                description="Drug has Investigational New Drug application",
                subject_types=["drug", "product"],
                object_types=["regulatory_filing"],
                required_level=1,
            ),
            # L2: Clinical and IP claims
            ClaimPredicate(
                name="in_clinical_trial",
                display_name="In Clinical Trial",
                description="Drug is in clinical trial phase",
                subject_types=["drug", "product"],
                object_types=["trial_phase"],
                required_level=2,
            ),
            ClaimPredicate(
                name="has_patent",
                display_name="Has Patent",
                description="Company/drug has patent protection",
                subject_types=["company", "drug", "product"],
                object_types=["patent"],
                required_level=2,
            ),
            ClaimPredicate(
                name="orphan_designation",
                display_name="Orphan Designation",
                description="Drug has orphan drug designation",
                subject_types=["drug", "product"],
                object_types=["designation"],
                required_level=2,
            ),
            ClaimPredicate(
                name="breakthrough_designation",
                display_name="Breakthrough Designation",
                description="Drug has breakthrough therapy designation",
                subject_types=["drug", "product"],
                object_types=["designation"],
                required_level=2,
            ),
            ClaimPredicate(
                name="fast_track_designation",
                display_name="Fast Track",
                description="Drug has fast track designation",
                subject_types=["drug", "product"],
                object_types=["designation"],
                required_level=2,
            ),
            # L3: Detailed regulatory claims
            ClaimPredicate(
                name="received_crl",
                display_name="Received CRL",
                description="Drug received Complete Response Letter",
                subject_types=["drug", "product"],
                object_types=["regulatory_action"],
                required_level=3,
            ),
            ClaimPredicate(
                name="fda_warning_letter",
                display_name="FDA Warning Letter",
                description="Facility received FDA warning letter",
                subject_types=["company", "facility"],
                object_types=["regulatory_action"],
                required_level=3,
            ),
            ClaimPredicate(
                name="clinical_hold",
                display_name="Clinical Hold",
                description="Trial placed on clinical hold",
                subject_types=["drug", "trial"],
                object_types=["regulatory_action"],
                required_level=3,
            ),
            ClaimPredicate(
                name="has_licensing_agreement",
                display_name="Licensing Agreement",
                description="Has drug licensing agreement",
                subject_types=["company"],
                object_types=["company", "agreement"],
                required_level=3,
            ),
            # L4: Forensic claims
            ClaimPredicate(
                name="data_integrity_issue",
                display_name="Data Integrity Issue",
                description="Clinical data integrity concerns",
                subject_types=["trial", "company"],
                object_types=["issue"],
                required_level=4,
            ),
            ClaimPredicate(
                name="manufacturing_deviation",
                display_name="Manufacturing Deviation",
                description="Manufacturing process deviation",
                subject_types=["facility", "product"],
                object_types=["deviation"],
                required_level=4,
            ),
        ]
        return [p for p in all_predicates if p.required_level <= level]

    def get_risk_categories(self, level: int = 2) -> list[RiskCategory]:
        """Get pharma-specific risk categories by extraction level."""
        if level < 2:
            return []

        all_risks = [
            # L2: Standard pharma risks
            RiskCategory(
                name="clinical_risk",
                display_name="Clinical Risk",
                description="Risk of clinical trial failure",
                indicators=[
                    "failed primary endpoint",
                    "safety signals",
                    "enrollment challenges",
                    "protocol amendments",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="regulatory_risk",
                display_name="Regulatory Risk",
                description="Risk of regulatory setback",
                indicators=[
                    "complete response letter",
                    "REMS requirements",
                    "post-market requirements",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="ip_risk",
                display_name="IP/Patent Risk",
                description="Intellectual property risks",
                indicators=[
                    "patent expiration",
                    "patent litigation",
                    "freedom to operate issues",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="competition_risk",
                display_name="Competition Risk",
                description="Competitive landscape risks",
                indicators=[
                    "multiple competitors in same indication",
                    "biosimilar threat",
                    "generic entry",
                ],
                required_level=2,
            ),
            # L3: Detailed risks
            RiskCategory(
                name="manufacturing_risk",
                display_name="Manufacturing Risk",
                description="Drug manufacturing risks",
                indicators=[
                    "single CMO dependency",
                    "supply chain issues",
                    "scale-up challenges",
                    "FDA warning letters",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="reimbursement_risk",
                display_name="Reimbursement Risk",
                description="Payer coverage/pricing risks",
                indicators=[
                    "ICER unfavorable review",
                    "formulary exclusions",
                    "price negotiations",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="safety_risk",
                display_name="Safety Risk",
                description="Drug safety concerns",
                indicators=[
                    "black box warning",
                    "serious adverse events",
                    "post-market safety signals",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="key_opinion_leader_risk",
                display_name="KOL Risk",
                description="Key opinion leader concerns",
                indicators=[
                    "negative KOL sentiment",
                    "competing therapy preference",
                ],
                required_level=3,
            ),
            # L4: Forensic risks
            RiskCategory(
                name="data_integrity_risk",
                display_name="Data Integrity Risk",
                description="Clinical data integrity concerns",
                indicators=[
                    "site inspection findings",
                    "data manipulation suspicions",
                    "GCP violations",
                ],
                required_level=4,
            ),
            RiskCategory(
                name="compliance_risk",
                display_name="Compliance Risk",
                description="Regulatory compliance concerns",
                indicators=[
                    "consent decree",
                    "corporate integrity agreement",
                    "DOJ investigation",
                ],
                required_level=4,
            ),
            RiskCategory(
                name="commercial_viability_risk",
                display_name="Commercial Viability Risk",
                description="Market/commercial risks",
                indicators=[
                    "market size overestimation",
                    "pricing pressure",
                    "patient access barriers",
                ],
                required_level=4,
            ),
        ]
        return [r for r in all_risks if r.required_level <= level]
