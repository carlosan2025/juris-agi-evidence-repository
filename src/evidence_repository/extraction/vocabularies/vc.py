"""Venture Capital vocabulary for startup due diligence extraction."""

from evidence_repository.extraction.vocabularies.base import (
    BaseVocabulary,
    ClaimPredicate,
    MetricDefinition,
    RiskCategory,
)


class VCVocabulary(BaseVocabulary):
    """VC/Startup due diligence vocabulary.

    Focused on metrics, claims, and risks relevant to venture capital
    investment decisions and startup evaluation.
    """

    @property
    def profile_code(self) -> str:
        return "vc"

    @property
    def profile_name(self) -> str:
        return "Venture Capital"

    def get_metrics(self, level: int = 1) -> list[MetricDefinition]:
        """Get VC-specific metrics by extraction level."""
        all_metrics = [
            # L1: Key startup metrics
            MetricDefinition(
                name="arr",
                display_name="ARR",
                description="Annual Recurring Revenue",
                unit_type="currency",
                aliases=["annual_recurring_revenue", "annualized_revenue"],
                required_level=1,
                calculation_notes="MRR × 12",
            ),
            MetricDefinition(
                name="mrr",
                display_name="MRR",
                description="Monthly Recurring Revenue",
                unit_type="currency",
                aliases=["monthly_recurring_revenue"],
                required_level=1,
            ),
            MetricDefinition(
                name="revenue",
                display_name="Revenue",
                description="Total revenue (including non-recurring)",
                unit_type="currency",
                aliases=["total_revenue", "gross_revenue"],
                required_level=1,
            ),
            MetricDefinition(
                name="burn",
                display_name="Burn Rate",
                description="Monthly cash burn rate",
                unit_type="currency",
                aliases=["burn_rate", "monthly_burn", "cash_burn"],
                required_level=1,
            ),
            MetricDefinition(
                name="runway",
                display_name="Runway",
                description="Months of runway remaining",
                unit_type="duration",
                aliases=["cash_runway", "months_runway"],
                required_level=1,
                calculation_notes="Cash / Monthly Burn",
            ),
            MetricDefinition(
                name="cash",
                display_name="Cash",
                description="Cash and cash equivalents",
                unit_type="currency",
                aliases=["cash_on_hand", "cash_position", "cash_balance"],
                required_level=1,
            ),
            MetricDefinition(
                name="headcount",
                display_name="Headcount",
                description="Total employees",
                unit_type="count",
                aliases=["employees", "team_size", "fte"],
                required_level=1,
            ),
            # L2: Growth and retention metrics
            MetricDefinition(
                name="growth_rate",
                display_name="Growth Rate",
                description="Revenue/ARR growth rate",
                unit_type="percentage",
                aliases=["revenue_growth", "arr_growth", "mom_growth", "yoy_growth"],
                required_level=2,
            ),
            MetricDefinition(
                name="nrr",
                display_name="NRR",
                description="Net Revenue Retention",
                unit_type="percentage",
                aliases=["net_revenue_retention", "net_dollar_retention", "ndr"],
                required_level=2,
                calculation_notes="(Starting MRR + Expansion - Contraction - Churn) / Starting MRR",
            ),
            MetricDefinition(
                name="grr",
                display_name="GRR",
                description="Gross Revenue Retention",
                unit_type="percentage",
                aliases=["gross_revenue_retention", "gross_dollar_retention"],
                required_level=2,
            ),
            MetricDefinition(
                name="churn",
                display_name="Churn Rate",
                description="Customer or revenue churn rate",
                unit_type="percentage",
                aliases=["churn_rate", "customer_churn", "logo_churn", "revenue_churn"],
                required_level=2,
            ),
            MetricDefinition(
                name="gross_margin",
                display_name="Gross Margin",
                description="Gross profit margin",
                unit_type="percentage",
                aliases=["gm", "gross_profit_margin"],
                required_level=2,
            ),
            # L3: Unit economics and efficiency
            MetricDefinition(
                name="cac",
                display_name="CAC",
                description="Customer Acquisition Cost",
                unit_type="currency",
                aliases=["customer_acquisition_cost", "acquisition_cost"],
                required_level=3,
            ),
            MetricDefinition(
                name="ltv",
                display_name="LTV",
                description="Customer Lifetime Value",
                unit_type="currency",
                aliases=["lifetime_value", "clv", "customer_lifetime_value"],
                required_level=3,
            ),
            MetricDefinition(
                name="ltv_cac_ratio",
                display_name="LTV/CAC Ratio",
                description="LTV to CAC ratio",
                unit_type="ratio",
                aliases=["ltv_cac", "ltv_to_cac"],
                required_level=3,
                calculation_notes="Target: >3x",
            ),
            MetricDefinition(
                name="cac_payback",
                display_name="CAC Payback",
                description="Months to recover CAC",
                unit_type="duration",
                aliases=["cac_payback_period", "payback_period"],
                required_level=3,
            ),
            MetricDefinition(
                name="magic_number",
                display_name="Magic Number",
                description="Sales efficiency metric",
                unit_type="ratio",
                aliases=["sales_efficiency"],
                required_level=3,
                calculation_notes="Net New ARR / S&M Spend (previous quarter)",
            ),
            MetricDefinition(
                name="arpu",
                display_name="ARPU",
                description="Average Revenue Per User",
                unit_type="currency",
                aliases=["average_revenue_per_user", "arpc", "average_revenue_per_customer"],
                required_level=3,
            ),
            MetricDefinition(
                name="dau",
                display_name="DAU",
                description="Daily Active Users",
                unit_type="count",
                aliases=["daily_active_users"],
                required_level=3,
            ),
            MetricDefinition(
                name="mau",
                display_name="MAU",
                description="Monthly Active Users",
                unit_type="count",
                aliases=["monthly_active_users"],
                required_level=3,
            ),
            # L4: Advanced metrics
            MetricDefinition(
                name="burn_multiple",
                display_name="Burn Multiple",
                description="Net burn divided by net new ARR",
                unit_type="ratio",
                aliases=["efficiency_score"],
                required_level=4,
                calculation_notes="Net Burn / Net New ARR (lower is better)",
            ),
            MetricDefinition(
                name="rule_of_40",
                display_name="Rule of 40",
                description="Growth rate + profit margin",
                unit_type="percentage",
                aliases=["rule_of_40_score"],
                required_level=4,
                calculation_notes="Revenue Growth % + EBITDA Margin %",
            ),
            MetricDefinition(
                name="quick_ratio",
                display_name="Quick Ratio (SaaS)",
                description="SaaS Quick Ratio",
                unit_type="ratio",
                aliases=["saas_quick_ratio"],
                required_level=4,
                calculation_notes="(New MRR + Expansion MRR) / (Contraction MRR + Churn MRR)",
            ),
        ]
        return [m for m in all_metrics if m.required_level <= level]

    def get_claim_predicates(self, level: int = 1) -> list[ClaimPredicate]:
        """Get VC-specific claim predicates by extraction level."""
        all_predicates = [
            # L1: Basic compliance claims
            ClaimPredicate(
                name="has_soc2",
                display_name="Has SOC2",
                description="Company has SOC2 certification",
                subject_types=["company"],
                object_types=["certification"],
                required_level=1,
            ),
            ClaimPredicate(
                name="is_iso27001",
                display_name="ISO 27001 Certified",
                description="Company has ISO 27001 certification",
                subject_types=["company"],
                object_types=["certification"],
                required_level=1,
            ),
            ClaimPredicate(
                name="is_gdpr_compliant",
                display_name="GDPR Compliant",
                description="Company claims GDPR compliance",
                subject_types=["company", "product"],
                object_types=["regulation"],
                required_level=1,
            ),
            ClaimPredicate(
                name="is_hipaa_compliant",
                display_name="HIPAA Compliant",
                description="Company claims HIPAA compliance",
                subject_types=["company", "product"],
                object_types=["regulation"],
                required_level=1,
            ),
            # L2: Business claims
            ClaimPredicate(
                name="owns_ip",
                display_name="Owns IP",
                description="Company owns intellectual property",
                subject_types=["company", "founder"],
                object_types=["patent", "trademark", "copyright", "trade_secret"],
                required_level=2,
            ),
            ClaimPredicate(
                name="has_customer",
                display_name="Has Customer",
                description="Company has specific customer",
                subject_types=["company"],
                object_types=["company", "organization"],
                required_level=2,
            ),
            ClaimPredicate(
                name="has_partnership",
                display_name="Has Partnership",
                description="Company has partnership agreement",
                subject_types=["company"],
                object_types=["company", "organization"],
                required_level=2,
            ),
            ClaimPredicate(
                name="raised_funding",
                display_name="Raised Funding",
                description="Company raised funding round",
                subject_types=["company"],
                object_types=["funding_round"],
                required_level=2,
            ),
            # L3: Detailed claims
            ClaimPredicate(
                name="has_security_incident",
                display_name="Security Incident",
                description="Company experienced security incident",
                subject_types=["company"],
                object_types=["incident"],
                required_level=3,
            ),
            ClaimPredicate(
                name="has_pending_litigation",
                display_name="Pending Litigation",
                description="Company has pending litigation",
                subject_types=["company", "founder"],
                object_types=["litigation"],
                required_level=3,
            ),
            ClaimPredicate(
                name="founder_prior_exit",
                display_name="Founder Prior Exit",
                description="Founder has prior successful exit",
                subject_types=["founder"],
                object_types=["company", "exit_event"],
                required_level=3,
            ),
            # L4: Forensic claims
            ClaimPredicate(
                name="related_party_transaction",
                display_name="Related Party Transaction",
                description="Related party transaction exists",
                subject_types=["company", "founder", "investor"],
                object_types=["transaction"],
                required_level=4,
            ),
            ClaimPredicate(
                name="cap_table_issue",
                display_name="Cap Table Issue",
                description="Cap table has issues",
                subject_types=["company"],
                object_types=["issue"],
                required_level=4,
            ),
        ]
        return [p for p in all_predicates if p.required_level <= level]

    def get_risk_categories(self, level: int = 2) -> list[RiskCategory]:
        """Get VC-specific risk categories by extraction level."""
        if level < 2:
            return []

        all_risks = [
            # L2: Standard VC risks
            RiskCategory(
                name="runway_risk",
                display_name="Runway Risk",
                description="Risk of running out of cash",
                indicators=[
                    "runway < 12 months",
                    "increasing burn rate",
                    "missed fundraising targets",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="customer_concentration",
                display_name="Customer Concentration",
                description="Over-reliance on few customers",
                indicators=[
                    "single customer > 20% revenue",
                    "top 3 customers > 50% revenue",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="key_person_risk",
                display_name="Key Person Risk",
                description="Dependency on key individuals",
                indicators=[
                    "single founder",
                    "no succession plan",
                    "critical knowledge in one person",
                ],
                required_level=2,
            ),
            RiskCategory(
                name="compliance_gap",
                display_name="Compliance Gap",
                description="Missing required certifications",
                indicators=[
                    "enterprise sales without SOC2",
                    "healthcare vertical without HIPAA",
                    "EU customers without GDPR compliance",
                ],
                required_level=2,
            ),
            # L3: Detailed risks
            RiskCategory(
                name="ip_risk",
                display_name="IP Risk",
                description="Intellectual property risks",
                indicators=[
                    "IP not assigned to company",
                    "founder IP from prior employer",
                    "open source license conflicts",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="market_risk",
                display_name="Market Risk",
                description="Market/competitive risks",
                indicators=[
                    "declining TAM",
                    "well-funded competitors",
                    "regulatory headwinds",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="technical_debt",
                display_name="Technical Debt",
                description="Technical/product risks",
                indicators=[
                    "legacy architecture",
                    "security vulnerabilities",
                    "scalability concerns",
                ],
                required_level=3,
            ),
            RiskCategory(
                name="churn_risk",
                display_name="Churn Risk",
                description="Customer retention risks",
                indicators=[
                    "NRR < 100%",
                    "increasing churn trend",
                    "low customer satisfaction",
                ],
                required_level=3,
            ),
            # L4: Forensic risks
            RiskCategory(
                name="governance_risk",
                display_name="Governance Risk",
                description="Corporate governance concerns",
                indicators=[
                    "related party transactions",
                    "board composition issues",
                    "missing controls",
                ],
                required_level=4,
            ),
            RiskCategory(
                name="financial_irregularity",
                display_name="Financial Irregularity",
                description="Accounting/financial concerns",
                indicators=[
                    "revenue recognition issues",
                    "expense timing manipulation",
                    "inconsistent metrics",
                ],
                required_level=4,
            ),
            RiskCategory(
                name="cap_table_risk",
                display_name="Cap Table Risk",
                description="Capitalization issues",
                indicators=[
                    "option pool too small",
                    "liquidation preference stacking",
                    "founder dilution",
                ],
                required_level=4,
            ),
        ]
        return [r for r in all_risks if r.required_level <= level]
