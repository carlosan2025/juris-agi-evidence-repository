"""Insurance underwriting vocabulary for due diligence extraction."""

from evidence_repository.extraction.vocabularies.base import (
    BaseVocabulary,
    ClaimPredicate,
    MetricDefinition,
    RiskCategory,
)


class InsuranceVocabulary(BaseVocabulary):
    """Insurance underwriting vocabulary.

    Focused on metrics, claims, and risks relevant to insurance
    underwriting, risk assessment, and regulatory compliance.
    """

    @property
    def profile_code(self) -> str:
        return "insurance"

    @property
    def profile_name(self) -> str:
        return "Insurance"

    def get_metrics(self, level: int = 1) -> list[MetricDefinition]:
        """Get insurance-specific metrics by extraction level."""
        all_metrics = [
            # L1: Basic financial metrics
            MetricDefinition(
                name="revenue",
                display_name="Revenue",
                description="Total revenue / gross written premium",
                unit_type="currency",
                aliases=["gwp", "gross_written_premium", "premium_income"],
                required_level=1,
            ),
            MetricDefinition(
                name="net_income",
                display_name="Net Income",
                description="Net income / profit",
                unit_type="currency",
                aliases=["profit", "earnings"],
                required_level=1,
            ),
            MetricDefinition(
                name="assets",
                display_name="Total Assets",
                description="Total assets under management",
                unit_type="currency",
                aliases=["total_assets", "aum"],
                required_level=1,
            ),
            MetricDefinition(
                name="policyholder_surplus",
                display_name="Policyholder Surplus",
                description="Policyholder surplus / capital",
                unit_type="currency",
                aliases=["surplus", "statutory_surplus", "capital"],
                required_level=1,
            ),
            MetricDefinition(
                name="policy_count",
                display_name="Policy Count",
                description="Number of active policies",
                unit_type="count",
                aliases=["policies_in_force", "active_policies"],
                required_level=1,
            ),
            # L2: Key ratios and performance metrics
            MetricDefinition(
                name="combined_ratio",
                display_name="Combined Ratio",
                description="Loss ratio + expense ratio",
                unit_type="percentage",
                aliases=["cr"],
                required_level=2,
                calculation_notes="< 100% indicates underwriting profit",
            ),
            MetricDefinition(
                name="loss_ratio",
                display_name="Loss Ratio",
                description="Incurred losses / earned premium",
                unit_type="percentage",
                aliases=["lr", "claims_ratio"],
                required_level=2,
            ),
            MetricDefinition(
                name="expense_ratio",
                display_name="Expense Ratio",
                description="Underwriting expenses / written premium",
                unit_type="percentage",
                aliases=["er"],
                required_level=2,
            ),
            MetricDefinition(
                name="rbc_ratio",
                display_name="RBC Ratio",
                description="Risk-Based Capital ratio",
                unit_type="percentage",
                aliases=["risk_based_capital", "rbc"],
                required_level=2,
                calculation_notes="Regulatory minimum is 200%",
            ),
            MetricDefinition(
                name="investment_yield",
                display_name="Investment Yield",
                description="Return on invested assets",
                unit_type="percentage",
                aliases=["investment_return", "portfolio_yield"],
                required_level=2,
            ),
            # L3: Detailed performance metrics
            MetricDefinition(
                name="roe",
                display_name="Return on Equity",
                description="Return on shareholders' equity",
                unit_type="percentage",
                aliases=["return_on_equity"],
                required_level=3,
            ),
            MetricDefinition(
                name="retention_ratio",
                display_name="Retention Ratio",
                description="Policy retention/renewal rate",
                unit_type="percentage",
                aliases=["renewal_rate", "policy_retention"],
                required_level=3,
            ),
            MetricDefinition(
                name="claims_frequency",
                display_name="Claims Frequency",
                description="Claims per policy period",
                unit_type="ratio",
                aliases=["frequency"],
                required_level=3,
            ),
            MetricDefinition(
                name="claims_severity",
                display_name="Claims Severity",
                description="Average claim amount",
                unit_type="currency",
                aliases=["average_claim", "severity"],
                required_level=3,
            ),
            MetricDefinition(
                name="reserves",
                display_name="Loss Reserves",
                description="Total loss reserves",
                unit_type="currency",
                aliases=["loss_reserves", "claim_reserves"],
                required_level=3,
            ),
            MetricDefinition(
                name="reserve_development",
                display_name="Reserve Development",
                description="Prior year reserve development",
                unit_type="currency",
                aliases=["pyd", "reserve_redundancy"],
                required_level=3,
            ),
            # L4: Advanced actuarial metrics
            MetricDefinition(
                name="ibnr",
                display_name="IBNR",
                description="Incurred But Not Reported reserves",
                unit_type="currency",
                aliases=["incurred_but_not_reported"],
                required_level=4,
            ),
            MetricDefinition(
                name="pml",
                display_name="Probable Maximum Loss",
                description="Probable Maximum Loss estimate",
                unit_type="currency",
                aliases=["probable_maximum_loss"],
                required_level=4,
            ),
            MetricDefinition(
                name="var",
                display_name="Value at Risk",
                description="Value at Risk for portfolio",
                unit_type="currency",
                aliases=["value_at_risk"],
                required_level=4,
            ),
            MetricDefinition(
                name="cat_exposure",
                display_name="Catastrophe Exposure",
                description="Total catastrophe exposure",
                unit_type="currency",
                aliases=["catastrophe_exposure", "cat_aggregate"],
                required_level=4,
            ),
        ]
        return [m for m in all_metrics if m.required_level <= level]

    def get_claim_predicates(self, level: int = 1) -> list[ClaimPredicate]:
        """Get insurance-specific claim predicates by extraction level."""
        all_predicates = [
            # L1: Basic regulatory claims
            ClaimPredicate(
                name="licensed_in",
                display_name="Licensed In",
                description="Company licensed to operate in jurisdiction",
                subject_types=["company"],
                object_types=["jurisdiction", "state"],
                required_level=1,
            ),
            ClaimPredicate(
                name="am_best_rating",
                display_name="AM Best Rating",
                description="Company has AM Best rating",
                subject_types=["company"],
                object_types=["rating"],
                required_level=1,
            ),
            ClaimPredicate(
                name="sp_rating",
                display_name="S&P Rating",
                description="Company has S&P rating",
                subject_types=["company"],
                object_types=["rating"],
                required_level=1,
            ),
            ClaimPredicate(
                name="offers_line",
                display_name="Offers Line of Business",
                description="Company writes specific line of insurance",
                subject_types=["company"],
                object_types=["line_of_business"],
                required_level=1,
            ),
            # L2: Operational claims
            ClaimPredicate(
                name="has_reinsurance",
                display_name="Has Reinsurance",
                description="Company has reinsurance arrangement",
                subject_types=["company"],
                object_types=["reinsurer", "treaty"],
                required_level=2,
            ),
            ClaimPredicate(
                name="regulatory_action",
                display_name="Regulatory Action",
                description="Company subject to regulatory action",
                subject_types=["company"],
                object_types=["action", "order"],
                required_level=2,
            ),
            ClaimPredicate(
                name="market_conduct_exam",
                display_name="Market Conduct Exam",
                description="Company underwent market conduct exam",
                subject_types=["company"],
                object_types=["exam", "finding"],
                required_level=2,
            ),
            ClaimPredicate(
                name="affiliated_with",
                display_name="Affiliated With",
                description="Company part of insurance group",
                subject_types=["company"],
                object_types=["company", "group"],
                required_level=2,
            ),
            # L3: Detailed regulatory claims
            ClaimPredicate(
                name="rate_filing_approved",
                display_name="Rate Filing Approved",
                description="Rate filing approved by regulator",
                subject_types=["company", "product"],
                object_types=["filing", "rate"],
                required_level=3,
            ),
            ClaimPredicate(
                name="form_filing_approved",
                display_name="Form Filing Approved",
                description="Policy form approved by regulator",
                subject_types=["company", "product"],
                object_types=["form"],
                required_level=3,
            ),
            ClaimPredicate(
                name="complaint_ratio",
                display_name="Complaint Ratio",
                description="Company complaint ratio vs industry",
                subject_types=["company"],
                object_types=["ratio", "ranking"],
                required_level=3,
            ),
            ClaimPredicate(
                name="consent_order",
                display_name="Consent Order",
                description="Company under consent order",
                subject_types=["company"],
                object_types=["order"],
                required_level=3,
            ),
            # L4: Forensic claims
            ClaimPredicate(
                name="reserve_deficiency",
                display_name="Reserve Deficiency",
                description="Actuarial reserve deficiency identified",
                subject_types=["company"],
                object_types=["deficiency"],
                required_level=4,
            ),
            ClaimPredicate(
                name="related_party_transaction",
                display_name="Related Party Transaction",
                description="Related party transaction exists",
                subject_types=["company"],
                object_types=["transaction"],
                required_level=4,
            ),
            ClaimPredicate(
                name="restatement",
                display_name="Financial Restatement",
                description="Financial statements restated",
                subject_types=["company"],
                object_types=["restatement"],
                required_level=4,
            ),
        ]
        return [p for p in all_predicates if p.required_level <= level]

    def get_risk_categories(self, level: int = 2) -> list[RiskCategory]:
        """Get insurance-specific risk categories by extraction level."""
        if level < 2:
            return []

        all_risks = [
            # L2: Standard insurance risks
            RiskCategory(
                name="underwriting_risk",
                display_name="Underwriting Risk",
                description="Risk from underwriting performance",
                indicators=[
                    "combined ratio > 100%",
                    "deteriorating loss ratio",
                    "inadequate pricing",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="reserve_risk",
                display_name="Reserve Risk",
                description="Risk of inadequate reserves",
                indicators=[
                    "adverse reserve development",
                    "IBNR uncertainty",
                    "long-tail exposure",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="capital_adequacy_risk",
                display_name="Capital Adequacy Risk",
                description="Risk of insufficient capital",
                indicators=[
                    "RBC ratio declining",
                    "surplus strain",
                    "high leverage",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="concentration_risk",
                display_name="Concentration Risk",
                description="Geographic or line of business concentration",
                indicators=[
                    "single state > 50% premium",
                    "single line dominance",
                    "large account dependency",
                ],
                required_level=2,
            ),
            # L3: Detailed risks
            RiskCategory(
                name="catastrophe_risk",
                display_name="Catastrophe Risk",
                description="Exposure to catastrophic events",
                indicators=[
                    "hurricane exposure",
                    "earthquake exposure",
                    "cyber aggregation",
                    "inadequate reinsurance",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="investment_risk",
                display_name="Investment Risk",
                description="Risk from investment portfolio",
                indicators=[
                    "credit downgrades",
                    "illiquid investments",
                    "duration mismatch",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="reinsurance_risk",
                display_name="Reinsurance Risk",
                description="Reinsurance counterparty/coverage risk",
                indicators=[
                    "reinsurer credit risk",
                    "coverage gaps",
                    "treaty exhaustion",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="regulatory_risk",
                display_name="Regulatory Risk",
                description="Risk from regulatory actions",
                indicators=[
                    "market conduct findings",
                    "rate disapprovals",
                    "consent orders",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="operational_risk",
                display_name="Operational Risk",
                description="Operational and systems risks",
                indicators=[
                    "system failures",
                    "vendor dependency",
                    "claims handling issues",
                ],
                required_level=3,
            ),
            # L4: Forensic risks
            RiskCategory(
                name="fraud_risk",
                display_name="Fraud Risk",
                description="Risk of fraudulent activity",
                indicators=[
                    "claims fraud patterns",
                    "agent misconduct",
                    "financial irregularities",
                ],
                required_level=4,
            ),
            RiskCategory(
                name="actuarial_risk",
                display_name="Actuarial Risk",
                description="Actuarial methodology concerns",
                indicators=[
                    "reserve methodology changes",
                    "assumption changes",
                    "actuarial opinion qualifications",
                ],
                required_level=4,
            ),
            RiskCategory(
                name="governance_risk",
                display_name="Governance Risk",
                description="Corporate governance concerns",
                indicators=[
                    "board composition",
                    "related party transactions",
                    "holding company issues",
                ],
                required_level=4,
            ),
            RiskCategory(
                name="run_off_risk",
                display_name="Run-off Risk",
                description="Risk from discontinued operations",
                indicators=[
                    "asbestos exposure",
                    "environmental claims",
                    "long-tail reserves",
                ],
                required_level=4,
            ),
        ]
        return [r for r in all_risks if r.required_level <= level]
